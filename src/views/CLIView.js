import inquirer from 'inquirer';
import chalk from 'chalk';
import ora from 'ora';
import { Config } from '../models/Config.js';

export class CLIView {
    constructor() {
        this.spinner = null;
    }

    printWelcome() {
        console.log(chalk.bold.cyan('🦞 Mini-Nebulus Agent'));
        console.log(chalk.gray(`Connected to ${Config.NEBULUS_BASE_URL} using ${Config.NEBULUS_MODEL}`));
        console.log('');
    }

    async promptUser() {
        const { prompt } = await inquirer.prompt([
            {
                type: 'input',
                name: 'prompt',
                message: chalk.green('You:'),
                prefix: '',
            },
        ]);
        return prompt.trim();
    }

    startSpinner(text) {
        if (this.spinner) this.spinner.stop();
        this.spinner = ora({ text, color: 'blue' }).start();
    }

    updateSpinner(text) {
        if (this.spinner) this.spinner.text = text;
    }

    stopSpinner() {
        if (this.spinner) this.spinner.stop();
        this.spinner = null;
    }

    succeedSpinner(text) {
        if (this.spinner) this.spinner.succeed(text);
        this.spinner = null;
    }

    failSpinner(text) {
        if (this.spinner) this.spinner.fail(text);
        this.spinner = null;
    }

    printAgentResponse(response) {
        if (response && response.trim()) {
            console.log(chalk.blue('Agent: ') + response.trim());
        }
    }

    printToolOutput(output) {
        const formattedOutput = output.trim().split('\n').map(line => `  ${line}`).join('\n');
        console.log(chalk.gray(formattedOutput));
    }

    printError(error) {
        console.error(chalk.red('\nError:'), error);
    }

    printGoodbye() {
        console.log(chalk.yellow('Goodbye!'));
    }
}
