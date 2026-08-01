import http from 'http';

import { readEnvFile } from './env.js';
import { logger } from './logger.js';

/**
 * Detect whether the host uses an API key or OAuth token.
 */
export function detectAuthMode(): 'api-key' | 'oauth' {
  const env = readEnvFile(['ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN']);
  if (process.env.CLAUDE_CODE_OAUTH_TOKEN || env.CLAUDE_CODE_OAUTH_TOKEN) {
    return 'oauth';
  }
  return 'api-key';
}

/**
 * Start a minimal credential proxy that injects the real API key / OAuth token
 * into container requests so containers never hold secrets directly.
 */
export async function startCredentialProxy(
  port: number,
  bindHost: string,
): Promise<http.Server> {
  const env = readEnvFile(['ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN']);
  const apiKey = process.env.ANTHROPIC_API_KEY || env.ANTHROPIC_API_KEY;
  const oauthToken =
    process.env.CLAUDE_CODE_OAUTH_TOKEN || env.CLAUDE_CODE_OAUTH_TOKEN;

  const server = http.createServer((req, res) => {
    // Simple pass-through proxy placeholder
    res.writeHead(502);
    res.end('credential proxy stub — configure OneCLI for full functionality');
  });

  return new Promise((resolve) => {
    server.listen(port, bindHost, () => {
      logger.info({ port, bindHost }, 'Credential proxy listening');
      resolve(server);
    });
  });
}
