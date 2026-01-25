import fs from 'fs/promises';
import path from 'path';
import chalk from 'chalk';

export class InputPreprocessor {
    static async process(input) {
        // Regex to find @filename. valid chars: alphanumeric, ., /, _, -
        const regex = /@([a-zA-Z0-9_./-]+)/g;
        const fileContents = [];

        const matches = [...input.matchAll(regex)];

        if (matches.length === 0) return input;

        for (const m of matches) {
            const token = m[0]; // @file
            const filePath = m[1]; // file

            try {
                const resolvedPath = path.resolve(process.cwd(), filePath);
                const stats = await fs.stat(resolvedPath);
                if (stats.isFile()) {
                    const content = await fs.readFile(resolvedPath, 'utf8');
                    fileContents.push(`\n--- Content from ${filePath} ---\n${content}\n--- End of ${filePath} ---\n`);
                    console.log(chalk.gray(`✔ Read file: ${filePath}`));
                } else {
                    console.warn(chalk.yellow(`⚠ Warning: ${filePath} is not a file.`));
                }
            } catch (err) {
                console.warn(chalk.yellow(`⚠ Warning: Could not read ${filePath}: ${err.message}`));
            }
        }

        if (fileContents.length > 0) {
            return input + '\n' + fileContents.join('\n');
        }

        return input;
    }
}
