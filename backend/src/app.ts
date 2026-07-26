import express from "express";
import cors from "cors";
import morgan from "morgan";
import multer from "multer";
import { buildApiRouter } from "./routes";
import firUploadRoute from "./routes/fir-upload.route";

export function createApp() {
  const app = express();

  app.use(cors());
  app.use(morgan("dev"));
  app.use(express.json());

  app.get("/health", (_req, res) => res.json({ status: "ok" }));

  

  // Excel upload/import feature (multipart, so mounted before express.json()
  // would matter for other routes, but multer parses its own body so order
  // relative to express.json() here is fine either way).
  app.use("/api", firUploadRoute);

  // Generic CRUD API for every table in the ER diagram.
  app.use("/api", buildApiRouter());

  // 404 fallback
  app.use((req, res) => {
    res.status(404).json({ error: `Route not found: ${req.method} ${req.originalUrl}` });
  });

  // Multer-specific errors (bad mimetype from fileFilter, file-too-large, etc.)
  // that escape the /fir/upload route handler land here as 400s; anything
  // else falls through to the generic error handler below.
  app.use(
    (err: any, _req: express.Request, res: express.Response, next: express.NextFunction) => {
      if (err instanceof multer.MulterError || /xlsx\/\.xls files are accepted/.test(err?.message ?? "")) {
        return res.status(400).json({ message: err.message ?? "Upload error" });
      }
      next(err);
    }
  );

  // Generic error handler
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    console.error(err);
    res.status(500).json({ error: err.message || "Internal server error" });
  });

  return app;
}
