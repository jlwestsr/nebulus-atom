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
      description: 'Executes a shell command on the local machine. Use this to list files, read contents, or perform system tasks.',
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
    content: 'You are a helpful AI assistant running on a local Nebulus server. You have access to a local shell via the \`run_shell_command\` tool. Use it when asked to perform file system operations or system tasks. You are concise and expert-level.' 
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

    if (prompt.toLowerCase() === 'exit' || prompt.toLowerCase() === 'quit') {
      console.log(chalk.yellow('Goodbye!'));
      process.exit(0);
    }

    history.push({ role: 'user', content: prompt });
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
      process.stdout.write(chalk.blue('Agent: '));

      let fullResponse = '';
      let toolCallsMap = {};
      let isFirstChunk = true;

      for await (const chunk of stream) {
        const delta = chunk.choices[0]?.delta;
        
        const content = delta?.content || '';
        if (content) {
            // Very basic heuristic: if it looks like JSON tool call starting, maybe don't stream it?
            // For now, we stream everything to keep it responsive.
            process.stdout.write(content);
            fullResponse += content;
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

      // Heuristic fallback for models that output JSON in content
      if (toolCalls.length === 0 && fullResponse.trim().startsWith('{') && fullResponse.trim().includes('"name":')) {
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
                  // If we detected it was a tool call, we clear the content for history
                  // so the model doesn't see redundant data.
                  fullResponse = ''; 
              }
          } catch (e) {}
      }

      if (toolCalls.length > 0) {
        console.log(''); // Ensure newline after streamed content

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