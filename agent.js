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

const exitCommands = ['exit', 'quit', '/exit', '/quit'];

const tools = [
  {
    type: 'function',
    function: {
      name: 'run_shell_command',
      description: 'Executes a shell command on the local machine.',
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
    content: 'You are Mini-Nebulus, a professional AI engineer CLI. You have full access to the local system via the run_shell_command tool. When asked to perform a task, EXECUTE the command immediately. Prefer detailed output (e.g., \`ls -la\`). If tree is missing, use \`find . -maxdepth 2 -not -path "*/.*"\`. DO NOT wrap tool calls in text; use the provided tool structure. CALL THE TOOL NOW.' 
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
    if (exitCommands.includes(input.toLowerCase())) {
      console.log(chalk.yellow('Goodbye!'));
      process.exit(0);
    }

    history.push({ role: 'user', content: input });
    await processTurn();
  }
}

function extractJson(text) {
    // 1. Try stripping markdown code blocks
    let clean = text.replace(/```\w*\n?/g, '').replace(/```$/g, '').trim();
    if (clean.startsWith('{') && clean.endsWith('}')) {
        try { return JSON.parse(clean); } catch(e) {}
    }

    // 2. Try regex for run_shell_command pattern
    const regex = /run_shell_command\s*\(\s*(\{[\s\S]*?\})\s*\)/;
    const match = text.match(regex);
    if (match) {
        try { return JSON.parse(match[1]); } catch(e) {}
    }

    // 3. Brute force JSON object search (first valid object with 'command')
    let startIndex = text.indexOf('{');
    while (startIndex !== -1) {
        let balance = 0;
        for (let i = startIndex; i < text.length; i++) {
            if (text[i] === '{') balance++;
            else if (text[i] === '}') balance--;
            
            if (balance === 0) {
                const jsonCand = text.substring(startIndex, i + 1);
                try {
                    const obj = JSON.parse(jsonCand);
                    if (obj.command || (obj.arguments && obj.arguments.command)) {
                        return obj; // Found it!
                    }
                    if (obj.name === 'run_shell_command') return obj;
                } catch (e) {}
                break; // Move to next starting brace
            }
        }
        startIndex = text.indexOf('{', startIndex + 1);
    }
    
    return null;
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

      let fullResponse = '';
      let toolCallsMap = {};

      for await (const chunk of stream) {
        const delta = chunk.choices[0]?.delta;
        if (delta?.content) fullResponse += delta.content;
        
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

      spinner.stop();

      let toolCalls = Object.values(toolCallsMap);

      // Heuristic extraction if no structured calls found
      if (toolCalls.length === 0) {
          const extracted = extractJson(fullResponse);
          if (extracted) {
             // Normalize the extracted object
             let args = extracted.arguments || extracted;
             // If it has 'command' at top level, treat as args
             if (extracted.command && !extracted.arguments) args = extracted;
             
             toolCalls = [{
                 id: `call_manual_${Date.now()}`,
                 type: 'function',
                 function: {
                     name: extracted.name || 'run_shell_command',
                     arguments: typeof args === 'string' ? args : JSON.stringify(args)
                 }
             }];
             // If we found a tool, we generally want to suppress the wrapper text 
             // unless it's very long/explanatory.
             if (fullResponse.length < 300) fullResponse = ''; 
          }
      }

      if (toolCalls.length > 0) {
        // Deduplicate
        const uniqueToolCalls = [];
        const seenCalls = new Set();
        for (const tc of toolCalls) {
            const key = `${tc.function.name}:${tc.function.arguments}`;
            if (!seenCalls.has(key)) {
                seenCalls.add(key);
                uniqueToolCalls.push(tc);
            }
        }
        
        // Add assistant response to history
        history.push({
            role: 'assistant',
            content: fullResponse.trim() || null,
            tool_calls: uniqueToolCalls.map(tc => ({ id: tc.id, type: tc.type, function: tc.function }))
        });

        // Print text response if it exists (and wasn't suppressed)
        if (fullResponse.trim()) {
            console.log(chalk.blue('Agent: ') + fullResponse.trim());
        }
        
        // Execute tools
        for (const tc of uniqueToolCalls) {
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
        // No tools, just print response
        if (fullResponse.trim()) {
             console.log(chalk.blue('Agent: ') + fullResponse.trim());
        }
        console.log('');
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