import type { NextApiRequest, NextApiResponse } from 'next';

const EXEC_SERVICE = process.env.NEXT_PUBLIC_EXEC_SERVICE_URL || process.env.EXEC_SERVICE_URL || 'http://localhost:8000';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const { proxy = [] } = req.query;
  const pathSegments = Array.isArray(proxy) ? proxy : [proxy];
  const targetPath = pathSegments.join('/');
  const queryString = typeof req.url === 'string' && req.url.includes('?')
    ? req.url.slice(req.url.indexOf('?'))
    : '';

  try {
    const url = `${EXEC_SERVICE}/auth/${targetPath}${queryString}`;

    const forwardResponse = await fetch(url, {
      method: req.method,
      headers: {
        'Content-Type': 'application/json',
        ...(req.headers.cookie ? { Cookie: req.headers.cookie } : {}),
      },
      body: req.method !== 'GET' && req.method !== 'HEAD' ? JSON.stringify(req.body) : undefined,
    });

    const setCookie = forwardResponse.headers.get('set-cookie');
    if (setCookie) {
      res.setHeader('Set-Cookie', setCookie);
    }

    const data = await forwardResponse.json();
    res.status(forwardResponse.status).json(data);
  } catch (err: unknown) {
    console.error('Auth proxy error:', err);
    res.status(502).json({ error: 'Auth service unavailable' });
  }
}

export const config = {
  api: {
    bodyParser: true,
  },
};
