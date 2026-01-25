import OpenAI from 'openai';
import dotenv from 'dotenv';
import inquirer from 'inquirer';
import chalk from 'chalk';

dotenv.config();

const client = new OpenAI({
  baseURL: process.env.NEBULUS_BASE_URL,
  apiKey: process.env.NEBULUS_API_KEY,
});

const model = process.env.NEBULUS_MODEL || 'qwen2.5-coder:latest';
const history = [
  { role: 'system', content: 'You are a helpful AI assistant running on a local Nebulus server. You are concise and expert-level.' }
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
    
    try {
      const stream = await client.chat.completions.create({
        model: model,
        messages: history,
        stream: true,
      });

      let fullResponse = '';

      for await (const chunk of stream) {
        const content = chunk.choices[0]?.delta?.content || '';
        process.stdout.write(content);
        fullResponse += content;
      }

      console.log('\n');
      history.push({ role: 'assistant', content: fullResponse });

    } catch (error) {
      console.error(chalk.red('\nError connecting to Nebulus:'), error.message);
    }
  }
}

chatLoop();
