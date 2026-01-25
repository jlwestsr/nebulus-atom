import { InputPreprocessor } from '../services/InputPreprocessor.js';
import { Config } from '../models/Config.js';
import { History } from '../models/History.js';
import { ToolRegistry } from '../models/ToolRegistry.js';
import { OpenAIService } from '../services/OpenAIService.js';
import { ToolExecutor } from '../services/ToolExecutor.js';
import { CLIView } from '../views/CLIView.js';

export class AgentController {
    constructor() {
        this.config = Config;
        this.history = new History(
            'You are Mini-Nebulus, a professional AI engineer CLI. You have full access to the local system via the run_shell_command tool. When asked to perform a task, EXECUTE the command immediately. Prefer detailed output (e.g., `ls -la`). If tree is missing, use `find . -maxdepth 2 -not -path "*/.*"`. DO NOT wrap tool calls in text; use the provided tool structure. CALL THE TOOL NOW.'
        );
        this.openAI = new OpenAIService();
        this.view = new CLIView();
        this.tools = ToolRegistry.getTools();
    }

    async start() {
        this.view.printWelcome();

        // Handle command line arguments as initial prompt
        const initialPrompt = process.argv.slice(2).join(' ').trim();
        if (initialPrompt) {
            const processed = await InputPreprocessor.process(initialPrompt);
            this.history.add('user', processed);
            console.log('You: ' + initialPrompt);
            await this.processTurn();
        }

        await this.chatLoop();
    }

    async chatLoop() {
        while (true) {
            const input = await this.view.promptUser();
            if (!input) continue;

            if (this.config.EXIT_COMMANDS.includes(input.toLowerCase())) {
                this.view.printGoodbye();
                process.exit(0);
            }

            const processed = await InputPreprocessor.process(input);
            this.history.add('user', processed);
            await this.processTurn();
        }
    }

    extractJson(text) {
        // 1. Try stripping markdown code blocks
        let clean = text.replace(/$/g, '').trim();
        if (clean.startsWith('{') && clean.endsWith('}')) {
            try { return JSON.parse(clean); } catch(e) {}
        }

        // 2. Try regex for run_shell_command pattern
        const regex = /run_shell_command\s*\(\s*(\{[^]*?\})\s*\)/;
        const match = text.match(regex);
        if (match) {
            try { return JSON.parse(match[1]); } catch(e) {}
        }

        // 3. Brute force JSON object search
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
                    break;
                }
            }
            startIndex = text.indexOf('{', startIndex + 1);
        }

        return null;
    }


    async start() {
        this.view.printWelcome();

        // Handle command line arguments as initial prompt
        const initialPrompt = process.argv.slice(2).join(' ').trim();
        if (initialPrompt) {
            this.history.add('user', initialPrompt);
            console.log('You: ' + initialPrompt);
            await this.processTurn();
        }

        await this.chatLoop();
    }

    async chatLoop() {
        while (true) {
            const input = await this.view.promptUser();
            if (!input) continue;

            if (this.config.EXIT_COMMANDS.includes(input.toLowerCase())) {
                this.view.printGoodbye();
                process.exit(0);
            }

            this.history.add('user', input);
            await this.processTurn();
        }
    }

    extractJson(text) {
        // 1. Try stripping markdown code blocks
        let clean = text.replace(/$/g, '').trim();
        if (clean.startsWith('{') && clean.endsWith('}')) {
            try { return JSON.parse(clean); } catch(e) {}
        }

        // 2. Try regex for run_shell_command pattern
        const regex = /run_shell_command\s*\(\s*(\{[^]*?\})\s*\)/;
        const match = text.match(regex);
        if (match) {
            try { return JSON.parse(match[1]); } catch(e) {}
        }

        // 3. Brute force JSON object search
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
                    break;
                }
            }
            startIndex = text.indexOf('{', startIndex + 1);
        }

        return null;
    }
    async start() {
        this.view.printWelcome();

        const initialPrompt = process.argv.slice(2).join(' ').trim();
        if (initialPrompt) {
            this.history.add('user', initialPrompt);
            console.log('You: ' + initialPrompt);
            await this.processTurn();
        }

        await this.chatLoop();
    }

    async chatLoop() {
        while (true) {
            const input = await this.view.promptUser();
            if (!input) continue;

            if (this.config.EXIT_COMMANDS.includes(input.toLowerCase())) {
                this.view.printGoodbye();
                process.exit(0);
            }

            this.history.add('user', input);
            await this.processTurn();
        }
    }

    extractJson(text) {
        // 1. Try stripping markdown code blocks
        let clean = text.replace(/\`\`\`\w*\n?/g, '').replace(/\`\`\`$/g, '').trim();
        if (clean.startsWith('{') && clean.endsWith('}')) {
            try { return JSON.parse(clean); } catch(e) {}
        }

        // 2. Try regex for run_shell_command pattern
        const regex = /run_shell_command\s*\(\s*(\{[\s\S]*?\})\s*\)/;
        const match = text.match(regex);
        if (match) {
            try { return JSON.parse(match[1]); } catch(e) {}
        }

        // 3. Brute force JSON object search
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
                    break;
                }
            }
            startIndex = text.indexOf('{', startIndex + 1);
        }

        return null;
    }

    async processTurn() {
        let finishedTurn = false;

        while (!finishedTurn) {
            this.view.startSpinner('Thinking...');
            try {
                const stream = await this.openAI.createChatCompletion(
                    this.history.get(),
                    this.tools
                );

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
                                    id: tc.id || 'call_' + Date.now() + '_' + index,
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

                this.view.stopSpinner();

                let toolCalls = Object.values(toolCallsMap);

                // Heuristic extraction
                if (toolCalls.length === 0) {
                    const extracted = this.extractJson(fullResponse);
                    if (extracted) {
                         let args = extracted.arguments || extracted;
                         if (extracted.command && !extracted.arguments) args = extracted;

                         toolCalls = [{
                             id: 'call_manual_' + Date.now(),
                             type: 'function',
                             function: {
                                 name: extracted.name || 'run_shell_command',
                                 arguments: typeof args === 'string' ? args : JSON.stringify(args)
                             }
                         }];
                         if (fullResponse.length < 300) fullResponse = '';
                    }
                }

                if (toolCalls.length > 0) {
                    // Deduplicate
                    const uniqueToolCalls = [];
                    const seenCalls = new Set();
                    for (const tc of toolCalls) {
                        const key = tc.function.name + ':' + tc.function.arguments;
                        if (!seenCalls.has(key)) {
                            seenCalls.add(key);
                            uniqueToolCalls.push(tc);
                        }
                    }

                    this.history.add('assistant', fullResponse.trim() || null, uniqueToolCalls.map(tc => ({ id: tc.id, type: tc.type, function: tc.function })));
                    this.view.printAgentResponse(fullResponse);

                    // Execute tools
                    for (const tc of uniqueToolCalls) {
                        this.view.startSpinner('Executing: ' + tc.function.name);
                        let output;
                        try {
                            const args = typeof tc.function.arguments === 'string' ? JSON.parse(tc.function.arguments) : tc.function.arguments;
                            const command = args.command;
                            this.view.updateSpinner('Executing: ' + command);

                            output = await ToolExecutor.execute(command);
                            this.view.succeedSpinner('Executed: ' + command);
                            this.view.printToolOutput(output);
                        } catch (e) {
                            output = 'Error: ' + e.message;
                            this.view.failSpinner('Failed: ' + e.message);
                        }
                        this.history.add('tool', output, null, tc.id);
                    }
                } else {
                    this.view.printAgentResponse(fullResponse);
                    console.log('');
                    this.history.add('assistant', fullResponse);
                    finishedTurn = true;
                }

            } catch (error) {
                this.view.stopSpinner();
                this.view.printError(error.message);
                finishedTurn = true;
            }
        }
    }
}
