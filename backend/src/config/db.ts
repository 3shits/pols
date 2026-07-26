// npm i pg
// npm i -D @types/pg
import { Pool, PoolConfig } from 'pg';

const config: PoolConfig = {
  host: process.env.DB_HOST ?? 'localhost',
  database: process.env.DB_NAME ?? 'police_fir',
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  port: process.env.DB_PORT ? Number(process.env.DB_PORT) : 5432,
  max: 10,
  idleTimeoutMillis: 30000,
  ssl:
    process.env.DB_SSL === 'true'
      ? { rejectUnauthorized: process.env.NODE_ENV === 'production' }
      : undefined,
};

export const pool = new Pool(config);

pool.on('error', (err) => {
  console.error('Unexpected PG pool error', err);
});
