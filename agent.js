import OpenAI from 'openai';
import dotenv from 'dotenv';
import inquirer from 'inquirer';
import chalk from 'chalk';
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
    content: 'You are a helpful AI assistant running on a local Nebulus server. You have access to a local shell via the `run_shell_command` tool. Use it when asked to perform file system operations or system tasks. You are concise and expert-level.' 
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
      },
    ]);

    if (prompt.toLowerCase() === 'exit' || prompt.toLowerCase() === 'quit') {
      console.log(chalk.yellow('Goodbye!'));
      process.exit(0);
    }

    history.push({ role: 'user', content: prompt });
    process.stdout.write(chalk.blue('Agent: '));

    await processTurn();
  }
}


async function processTurn() {
  let finishedTurn = false;
  
  while (!finishedTurn) {
    try {
      const stream = await client.chat.completions.create({
        model: model,
        messages: history,
        stream: true,
        tools: tools,
      });

      let fullResponse = '';
      let toolCallsMap = {};

      for await (const chunk of stream) {
        const delta = chunk.choices[0]?.delta;
        
        // Handle content
        const content = delta?.content || '';
        if (content) {
            process.stdout.write(content);
            fullResponse += content;
        }

        // Handle tool calls
        if (delta?.tool_calls) {
          for (const tc of delta.tool_calls) {
             const index = tc.index;
             if (!toolCallsMap[index]) {
               toolCallsMap[index] = { 
                 index: index,
                 id: tc.id || '',
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

      const toolCalls = Object.values(toolCallsMap);

      if (toolCalls.length > 0) {
        // If we printed content, add a newline
        if (fullResponse) console.log('');

        // Add assistant message with tool calls to history
        const assistantMessage = {
            role: 'assistant',
            content: fullResponse || null,
            tool_calls: toolCalls
        };
        history.push(assistantMessage);
        
        // Execute tools
        for (const tc of toolCalls) {
            if (tc.function.name === 'run_shell_command') {
                let output;
                let command;
                try {
                    const args = JSON.parse(tc.function.arguments);
                    command = args.command;
                    console.log(chalk.gray(`> Executing: ${command}`));
                    
                    const { stdout, stderr } = await execAsync(command);
                    output = stdout || stderr;
                    if (!output) output = '(no output)';
                } catch (e) {
                    output = `Error: ${e.message}`;
                }
                
                // Add tool result to history
                history.push({
                    role: 'tool',
                    tool_call_id: tc.id,
                    content: output
                });
            } else {
                console.log(chalk.red(`Unknown tool: ${tc.function.name}`));
            }
        }
        // Continue loop to get the final response based on tool outputs
      } else {
        // No tool calls, we are done
        console.log('\n');
        history.push({ role: 'assistant', content: fullResponse });
        finishedTurn = true;
      }

    } catch (error) {
      console.error(chalk.red('\nError connecting to Nebulus:'), error.message);
      finishedTurn = true;
    }
  }
}


chatLoop();

