import OpenAI from 'openai';
import dotenv from 'dotenv';
import inquirer from 'inquirer';
import chalk from 'chalk';
import ora from 'ora';
import { exec } from 'node:child_process';
import { promisify } from 'node:util';

dotenv.config();

const execAsync = promisify(exec);

const client = new OpenAI({
  baseURL: process.env.NEBULUS_BASE_URL,
  apiKey: process.env.NEBULUS_API_KEY,
});

const model = process.env.NEBULUS_MODEL || 'qwen2.5-coder:latest';

const tools = [
  {
    type: 'function',
    function: {
      name: 'run_shell_command',
      description: 'Executes a shell command on the local machine. Use this for file operations (ls, cat, mkdir), git commands, or system info.',
      parameters: {
        type: 'object',
        properties: {
          command: {
            type: 'string',
            description: 'The shell command to execute.',
          },
        },
        required: ['command'],
      },
    },
  },
];

const history = [
  { 
    role: 'system', 
    content: 'You are Mini-Nebulus, a professional AI engineer CLI. You have full access to the local system via the run_shell_command tool. When asked to perform a task, EXECUTE the command immediately using the tool. DO NOT write the tool call in markdown or text. DO NOT ask for confirmation. Just CALL the function.' 
  }
];

console.log(chalk.bold.cyan('🦞 Mini-Nebulus Agent'));
console.log(chalk.gray(`Connected to ${process.env.NEBULUS_BASE_URL} using ${model}`));
console.log('');

async function chatLoop() {
  while (true) {
    const { prompt } = await inquirer.prompt([
      {
        type: 'input',
        name: 'prompt',
        message: chalk.green('You:'),
        prefix: '',
      },
    ]);

    const input = prompt.trim();
    if (!input) continue;
    const exitCommands = ['exit', 'quit', '/exit', '/quit'];
    if (exitCommands.includes(input.toLowerCase())) {
      console.log(chalk.yellow('Goodbye!'));
      process.exit(0);
    }

    history.push({ role: 'user', content: input });
    await processTurn();
  }
}

async function processTurn() {
  let finishedTurn = false;
  
  while (!finishedTurn) {
    const spinner = ora({ text: 'Thinking...', color: 'blue' }).start();
    try {
      const stream = await client.chat.completions.create({
        model: model,
        messages: history,
        stream: true,
        tools: tools,
        tool_choice: 'auto',
      });

      spinner.stop();

      let fullResponse = '';
      let toolCallsMap = {};
      let hasStartedPrinting = false;

      for await (const chunk of stream) {
        const delta = chunk.choices[0]?.delta;
        
        const content = delta?.content || '';
        if (content) {
            fullResponse += content;
            const trimmed = fullResponse.trim();
            const looksLikeJson = trimmed.startsWith('{');
            
            // Heuristic: If it looks like it's starting a code block for a tool, delay printing
            const looksLikeCodeBlock = trimmed.includes('```') || trimmed.includes('run_shell_command');

            if (!looksLikeJson && !looksLikeCodeBlock) {
                if (!hasStartedPrinting) {
                    process.stdout.write(chalk.blue('Agent: '));
                    hasStartedPrinting = true;
                }
                process.stdout.write(content);
            }
        }

        if (delta?.tool_calls) {
          for (const tc of delta.tool_calls) {
             const index = tc.index;
             if (!toolCallsMap[index]) {
               toolCallsMap[index] = { 
                 index: index,
                 id: tc.id || `call_${Date.now()}_${index}`,
                 type: tc.type || 'function',
                 function: { name: '', arguments: '' } 
               };
             }
             if (tc.id) toolCallsMap[index].id = tc.id;
             if (tc.function?.name) toolCallsMap[index].function.name += tc.function.name;
             if (tc.function?.arguments) toolCallsMap[index].function.arguments += tc.function.arguments;
          }
        }
      }

      let toolCalls = Object.values(toolCallsMap);

      // 1. Check for pure JSON response (existing heuristic)
      if (toolCalls.length === 0 && fullResponse.trim().startsWith('{')) {
          try {
              const potentialTool = JSON.parse(fullResponse.trim());
              if (potentialTool.name && potentialTool.arguments) {
                  toolCalls = [{
                      id: `call_manual_${Date.now()}`,
                      type: 'function',
                      function: {
                          name: potentialTool.name,
                          arguments: typeof potentialTool.arguments === 'string' ? potentialTool.arguments : JSON.stringify(potentialTool.arguments)
                      }
                  }];
                  fullResponse = ''; 
              }
          } catch (e) {}
      }

      // 2. Check for Hallucinated Tool Calls in text (e.g. run_shell_command({...}))
      // Regex looks for: run_shell_command ( { command: ... } )
      if (toolCalls.length === 0) {
          const regex = /run_shell_command\s*\(\s*(\{.*?\})\s*\)/s;
          const match = fullResponse.match(regex);
          if (match) {
              try {
                  const jsonArgs = match[1];
                  const parsedArgs = JSON.parse(jsonArgs);
                  if (parsedArgs.command) {
                       toolCalls = [{
                          id: `call_regex_${Date.now()}`,
                          type: 'function',
                          function: {
                              name: 'run_shell_command',
                              arguments: JSON.stringify(parsedArgs)
                          }
                      }];
                      // We found the command, so we can suppress the hallucinated text
                      // But if there was introductory text, we might want to keep it?
                      // For now, let's keep the intro text but remove the code block if possible, 
                      // or just clear it if it's mostly the command.
                      if (fullResponse.length < 200) {
                          fullResponse = ''; // Assume it was just the command wrapper
                      }
                  }
              } catch (e) {
                  // Regex matched but JSON parse failed
              }
          }
      }

      // If we still have content that wasn't a tool call, and we suppressed it earlier, print it now.
      if (toolCalls.length === 0 && fullResponse && !hasStartedPrinting) {
          process.stdout.write(chalk.blue('Agent: '));
          process.stdout.write(fullResponse);
          hasStartedPrinting = true;
      }

      if (toolCalls.length > 0) {
        if (hasStartedPrinting) console.log('');

        history.push({
            role: 'assistant',
            content: fullResponse.trim() || null,
            tool_calls: toolCalls.map(tc => ({ id: tc.id, type: tc.type, function: tc.function }))
        });
        
        for (const tc of toolCalls) {
            const cmdSpinner = ora({ text: `Executing: ${tc.function.name}`, color: 'gray' }).start();
            let output;
            try {
                const args = typeof tc.function.arguments === 'string' ? JSON.parse(tc.function.arguments) : tc.function.arguments;
                const command = args.command;
                cmdSpinner.text = `Executing: ${command}`;
                
                const { stdout, stderr } = await execAsync(command);
                output = stdout || stderr || '(no output)';
                cmdSpinner.succeed(`Executed: ${command}`);
                
                const formattedOutput = output.trim().split('\n').map(line => `  ${line}`).join('\n');
                console.log(chalk.gray(formattedOutput));
                
            } catch (e) {
                output = `Error: ${e.message}`;
                cmdSpinner.fail(`Failed: ${e.message}`);
            }
            
            history.push({ role: 'tool', tool_call_id: tc.id, content: output });
        }
      } else {
        if (!hasStartedPrinting && fullResponse) {
             process.stdout.write(chalk.blue('Agent: ') + fullResponse);
        }
        console.log('\n');
        history.push({ role: 'assistant', content: fullResponse });
        finishedTurn = true;
      }

    } catch (error) {
      spinner.stop();
      console.error(chalk.red('\nError:'), error.message);
      finishedTurn = true;
    }
  }
}

async function main() {
    const initialPrompt = process.argv.slice(2).join(' ').trim();
    if (initialPrompt) {
        history.push({ role: 'user', content: initialPrompt });
        console.log(chalk.green('You: ') + initialPrompt);
        await processTurn();
    }
    
    await chatLoop();
}

main();