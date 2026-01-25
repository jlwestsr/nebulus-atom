import dotenv from 'dotenv';
dotenv.config();

export class Config {
    static get NEBULUS_BASE_URL() { return process.env.NEBULUS_BASE_URL; }
    static get NEBULUS_API_KEY() { return process.env.NEBULUS_API_KEY; }
    static get NEBULUS_MODEL() { return process.env.NEBULUS_MODEL || 'qwen2.5-coder:latest'; }
    static get EXIT_COMMANDS() { return ['exit', 'quit', '/exit', '/quit']; }
}
