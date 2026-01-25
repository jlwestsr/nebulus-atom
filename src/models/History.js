export class History {
    constructor(systemPrompt) {
        this.messages = [
            { role: 'system', content: systemPrompt }
        ];
    }

    add(role, content, tool_calls = null, tool_call_id = null) {
        const message = { role, content };
        if (tool_calls) message.tool_calls = tool_calls;
        if (tool_call_id) message.tool_call_id = tool_call_id;
        this.messages.push(message);
    }

    get() {
        return this.messages;
    }
}
