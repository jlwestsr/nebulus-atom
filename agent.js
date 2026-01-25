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
      description: 'Executes a shell command on the local machine. Use this for file operations (ls, cat, mkdir), git commands, or system info. DO NOT suggest commands in text; always execute them via this tool.',
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
    content: 'You are Mini-Nebulus, a professional AI engineer CLI. You have full access to the local system via the run_shell_command tool. When asked to perform a task (listing files, reading code, checking git), EXECUTE the command immediately using the tool. Do not ask for permission. Do not wrap commands in markdown code blocks if you intend to run them. If a command fails, try an alternative (e.g., if tree is missing, use ls -R).' 
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
    if (input.toLowerCase() === 'exit' || input.toLowerCase() === 'quit') {
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
            // Buffer-and-check: If response starts with '{', it might be a tool call in content.
            // We delay printing if we suspect it's JSON.
            fullResponse += content;
            
            const trimmed = fullResponse.trim();
            const looksLikeJson = trimmed.startsWith('{');
            
            if (!looksLikeJson) {
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

      // Fallback: If we didn't print anything because we thought it was JSON, 
      // check if it actually WAS a valid tool call.
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
          } catch (e) {
              // Not valid JSON tool call after all, print it now
              if (!hasStartedPrinting) {
                  process.stdout.write(chalk.blue('Agent: '));
                  process.stdout.write(fullResponse);
                  hasStartedPrinting = true;
              }
          }
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

chatLoop();