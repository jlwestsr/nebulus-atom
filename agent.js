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
    content: 'You are a helpful AI assistant running on a local Nebulus server. You have access to a local shell via the \`run_shell_command\` tool. Use it when asked to perform file system operations or system tasks. IMPORTANT: Always use the structured \`run_shell_command\` tool call. You are concise and expert-level.' 
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
        tool_choice: 'auto',
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

        // Handle structured tool calls
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

      // Heuristic: If model sent JSON in content instead of tool_calls
      if (toolCalls.length === 0 && fullResponse.trim().startsWith('{') && fullResponse.trim().includes('"name":')) {
          try {
              const potentialTool = JSON.parse(fullResponse.trim());
              if (potentialTool.name && potentialTool.arguments) {
                  toolCalls = [{
                      id: `call_manual_${Date.now()}`,
                      type: 'function',
                      function: {
                          name: potentialTool.name,
                          arguments: JSON.stringify(potentialTool.arguments) // Ensure arguments is a string
                      }
                  }];
                  // Clear fullResponse since it was just the tool call
                  fullResponse = '';
              }
          } catch (e) {
              // Not valid JSON tool call, ignore
          }
      }

      if (toolCalls.length > 0) {
        if (fullResponse) console.log('');

        const assistantMessage = {
            role: 'assistant',
            content: fullResponse || null,
            tool_calls: toolCalls.map(tc => ({
                id: tc.id,
                type: tc.type,
                function: tc.function
            }))
        };
        history.push(assistantMessage);
        
        for (const tc of toolCalls) {
            if (tc.function.name === 'run_shell_command') {
                let output;
                let command;
                try {
                    const args = typeof tc.function.arguments === 'string' 
                        ? JSON.parse(tc.function.arguments) 
                        : tc.function.arguments;
                    command = args.command;
                    console.log(chalk.gray(`> Executing: ${command}`));
                    
                    const { stdout, stderr } = await execAsync(command);
                    output = stdout || stderr;
                    if (!output) output = '(no output)';
                } catch (e) {
                    output = `Error: ${e.message}`;
                }
                
                history.push({
                    role: 'tool',
                    tool_call_id: tc.id,
                    content: output
                });
            } else {
                console.log(chalk.red(`Unknown tool: ${tc.function.name}`));
                history.push({
                    role: 'tool',
                    tool_call_id: tc.id,
                    content: `Error: Unknown tool ${tc.function.name}`
                });
            }
        }
      } else {
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