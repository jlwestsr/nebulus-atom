import { exec } from 'node:child_process';
import { promisify } from 'node:util';

const execAsync = promisify(exec);

export class ToolExecutor {
    static async execute(command) {
        try {
            const { stdout, stderr } = await execAsync(command);
            return stdout || stderr || '(no output)';
        } catch (e) {
            return `Error: ${e.message}`;
        }
    }
}
