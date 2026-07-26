// npm i express multer
// npm i -D @types/express @types/multer
import { Router, Request, Response } from 'express';
import multer from 'multer';
import { uploadWorkbookToStratus, downloadWorkbookFromStratus } from '../config/catalyst';
import { parseFirWorkbook } from '../services/excelParser';
import { importParsedWorkbook } from '../services/firImportService';
import { UploadResponse } from '../types/fir.types';

const router = Router();

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 25 * 1024 * 1024 }, // 25 MB
  fileFilter: (_req, file, cb) => {
    const allowed = [
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // .xlsx
      'application/vnd.ms-excel', // .xls
    ];
    if (!allowed.includes(file.mimetype)) {
      return cb(new Error('Only .xlsx/.xls files are accepted'));
    }
    cb(null, true);
  },
});

/**
 * POST /api/fir/upload
 * multipart/form-data, field name "file"
 *
 * Flow:
 *  1. Receive the workbook via multer (in-memory buffer).
 *  2. Upload the raw file to Catalyst Stratus FIRST - this is the
 *     durable, auditable copy of what was submitted.
 *  3. Re-download it from Stratus (so parsing is always driven off the
 *     persisted object, not the transient upload buffer) and parse it.
 *  4. Resolve lookups and insert into Postgres, one FIR/case per DB
 *     transaction, and report per-case success/failure.
 */
router.post('/fir/upload', upload.single('file'), async (req: Request, res: Response) => {
  if (!req.file) {
    return res.status(400).json({ message: 'No file uploaded. Expected field name "file".' });
  }

  try {
    const { objectKey, objectUrl } = await uploadWorkbookToStratus(
      req,
      req.file.buffer,
      req.file.originalname
    );

    const workbookBuffer = await downloadWorkbookFromStratus(req, objectKey);
    const parsed = await parseFirWorkbook(workbookBuffer);

    const { results, errors } = await importParsedWorkbook(parsed);

    const response: UploadResponse = {
      stratusObjectKey: objectKey,
      stratusObjectUrl: objectUrl,
      totalCases: parsed.caseMaster.length,
      results,
      errors,
    };

    const statusCode = errors.length === 0 ? 201 : errors.length === results.length ? 422 : 207;
    return res.status(statusCode).json(response);
  } catch (err) {
    console.error('FIR upload failed:', err);
    return res.status(500).json({
      message: 'Failed to process the uploaded workbook.',
      error: err instanceof Error ? err.message : String(err),
    });
  }
});

export default router;
