export class ToolRegistry {
    static getTools() {
        return [
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
    }
}
