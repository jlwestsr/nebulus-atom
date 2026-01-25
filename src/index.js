import { AgentController } from './controllers/AgentController.js';

const agent = new AgentController();
agent.start().catch(err => {
    console.error('Fatal Error:', err);
    process.exit(1);
});
