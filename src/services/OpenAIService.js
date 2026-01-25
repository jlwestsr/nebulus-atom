import OpenAI from 'openai';
import { Config } from '../models/Config.js';

export class OpenAIService {
    constructor() {
        this.client = new OpenAI({
            baseURL: Config.NEBULUS_BASE_URL,
            apiKey: Config.NEBULUS_API_KEY,
        });
        this.model = Config.NEBULUS_MODEL;
    }

    async createChatCompletion(messages, tools) {
        return await this.client.chat.completions.create({
            model: this.model,
            messages: messages,
            stream: true,
            tools: tools,
            tool_choice: 'auto',
        });
    }
}
