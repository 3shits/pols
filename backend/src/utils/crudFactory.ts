import { Router, Request, Response } from "express";
import { pool } from "../config/db";

export interface TableConfig {
  /** Express path segment, e.g. "case-master" */
  resource: string;
  /** Actual PostgreSQL table name, e.g. "CaseMaster" */
  table: string;
  /** Primary key column name, e.g. "CaseMasterID" */
  pk: string;
  /** All writable columns (excludes pk if it's auto-generated via SERIAL, unless pk is a natural/manual key) */
  columns: string[];
  /** Whether the PK must be supplied on insert (true for natural keys like ActCode) */
  manualPk?: boolean;
}

const q = (id: string) => `"${id}"`;

function buildWhereFromQuery(
  config: TableConfig,
  query: Record<string, unknown>
): { clause: string; values: unknown[] } {
  const allowed = new Set([...config.columns, config.pk]);
  const conditions: string[] = [];
  const values: unknown[] = [];
  let i = 1;

  for (const [key, val] of Object.entries(query)) {
    if (key === "limit" || key === "offset" || key === "sort" || key === "order") continue;
    if (!allowed.has(key) || val === undefined) continue;
    conditions.push(`${q(key)} = $${i}`);
    values.push(val);
    i++;
  }

  return {
    clause: conditions.length ? `WHERE ${conditions.join(" AND ")}` : "",
    values,
  };
}

export function createCrudRouter(config: TableConfig): Router {
  const router = Router();
  const { table, pk, columns } = config;
  const insertableColumns = config.manualPk ? [pk, ...columns] : columns;

  // ---- GET /resource  (list, with optional ?Column=value filters, pagination) ----
  router.get("/", async (req: Request, res: Response) => {
    try {
      const limit = Math.min(Number(req.query.limit) || 100, 500);
      const offset = Number(req.query.offset) || 0;
      const { clause, values } = buildWhereFromQuery(config, req.query as Record<string, unknown>);

      const sql = `SELECT * FROM ${q(table)} ${clause} ORDER BY ${q(pk)} LIMIT $${values.length + 1} OFFSET $${values.length + 2}`;
      const result = await pool.query(sql, [...values, limit, offset]);

      const countResult = await pool.query(`SELECT COUNT(*) FROM ${q(table)} ${clause}`, values);
      res.json({
        data: result.rows,
        total: Number(countResult.rows[0].count),
        limit,
        offset,
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // ---- GET /resource/:id ----
  router.get("/:id", async (req: Request, res: Response) => {
    try {
      const sql = `SELECT * FROM ${q(table)} WHERE ${q(pk)} = $1`;
      const result = await pool.query(sql, [req.params.id]);
      if (result.rows.length === 0) {
        return res.status(404).json({ error: `${table} with ${pk}=${req.params.id} not found` });
      }
      res.json(result.rows[0]);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // ---- POST /resource ----
  router.post("/", async (req: Request, res: Response) => {
    try {
      const body = req.body || {};
      const cols = insertableColumns.filter((c) => body[c] !== undefined);
      if (cols.length === 0) {
        return res.status(400).json({ error: "No valid columns supplied in request body" });
      }
      const placeholders = cols.map((_, idx) => `$${idx + 1}`);
      const values = cols.map((c) => body[c]);

      const sql = `INSERT INTO ${q(table)} (${cols.map(q).join(", ")}) VALUES (${placeholders.join(", ")}) RETURNING *`;
      const result = await pool.query(sql, values);
      res.status(201).json(result.rows[0]);
    } catch (err: any) {
      res.status(400).json({ error: err.message });
    }
  });

  // ---- PUT /resource/:id  (partial update) ----
  router.put("/:id", async (req: Request, res: Response) => {
    try {
      const body = req.body || {};
      const cols = columns.filter((c) => body[c] !== undefined);
      if (cols.length === 0) {
        return res.status(400).json({ error: "No valid columns supplied in request body" });
      }
      const setClause = cols.map((c, idx) => `${q(c)} = $${idx + 1}`).join(", ");
      const values = cols.map((c) => body[c]);
      values.push(req.params.id);

      const sql = `UPDATE ${q(table)} SET ${setClause} WHERE ${q(pk)} = $${values.length} RETURNING *`;
      const result = await pool.query(sql, values);
      if (result.rows.length === 0) {
        return res.status(404).json({ error: `${table} with ${pk}=${req.params.id} not found` });
      }
      res.json(result.rows[0]);
    } catch (err: any) {
      res.status(400).json({ error: err.message });
    }
  });

  // ---- DELETE /resource/:id ----
  router.delete("/:id", async (req: Request, res: Response) => {
    try {
      const sql = `DELETE FROM ${q(table)} WHERE ${q(pk)} = $1 RETURNING *`;
      const result = await pool.query(sql, [req.params.id]);
      if (result.rows.length === 0) {
        return res.status(404).json({ error: `${table} with ${pk}=${req.params.id} not found` });
      }
      res.json({ deleted: result.rows[0] });
    } catch (err: any) {
      res.status(400).json({ error: err.message });
    }
  });

  return router;
}
