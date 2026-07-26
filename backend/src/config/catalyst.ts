import type { Request } from 'express';
// npm i zcatalyst-sdk-node
import catalyst from 'zcatalyst-sdk-node';

const STRATUS_BUCKET_NAME = process.env.CATALYST_STRATUS_BUCKET ?? 'pols-excel';

/**
 * Catalyst's Node SDK is request-scoped: it reads the execution context
 * (auth, project scope) off the incoming request, so we initialize per-request
 * rather than once at module load.
 *
 * Your 'pols-excel' bucket is ACL'd to "authenticated Catalyst users only".
 * That ACL governs direct/user-scope access (e.g. a browser calling Stratus
 * itself). This backend talks to Stratus server-to-server, so we initialize
 * with { scope: 'admin' } explicitly - Admin scope has unrestricted access
 * and bypasses that user-facing ACL, so the bucket can stay private/
 * authenticated-only and nothing else needs to change for that setting.
 * (Admin is actually the SDK default even without passing scope, but we
 * spell it out here so it's obvious why this works against a restricted
 * bucket.)
 *
 * The one real requirement: `req` must carry a genuine Catalyst execution
 * context, which only exists when this app is deployed on Catalyst
 * (Advanced I/O Function or AppSail) - not when run as a plain standalone
 * Express server elsewhere. See src/server.ts for the matching port change.
 */
export function getStratusBucket(req: Request) {
  const app = catalyst.initialize(req as unknown as { [x: string]: unknown }, {
    scope: 'admin',
  });
  // NOTE: as of zcatalyst-sdk-node@2.5.1 (latest on npm at the time of writing),
  // the published TypeScript types only expose `.filestore()`, not `.stratus()`.
  // Stratus itself is live per Catalyst's docs, but SDK typings haven't caught
  // up yet in the published package, so we cast through `any` here. If your
  // installed SDK version has `.stratus()` typed, drop the cast.
  const stratus = (app as any).stratus();
  return stratus.bucket(STRATUS_BUCKET_NAME);
}

/**
 * Uploads the raw workbook buffer to Stratus under a collision-proof key.
 * Returns the object key (path within the bucket) that was written.
 */
export async function uploadWorkbookToStratus(
  req: Request,
  fileBuffer: Buffer,
  originalFileName: string
): Promise<{ objectKey: string; objectUrl?: string }> {
  const bucket = getStratusBucket(req);

  const safeName = originalFileName.replace(/[^a-zA-Z0-9._-]/g, '_');
  const objectKey = `fir-imports/${Date.now()}-${safeName}`;

  const putOptions = {
    overwrite: false,
    type:
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  };

  const result = await bucket.putObject(objectKey, fileBuffer, putOptions);

  return {
    objectKey,
    objectUrl: (result as any)?.object_url ?? (result as any)?.objectURL,
  };
}

/**
 * Re-downloads the object we just uploaded so parsing always happens off
 * the persisted copy in Stratus rather than the transient multer buffer.
 * This guarantees "uploaded first, then parsed from storage" semantics.
 */
export async function downloadWorkbookFromStratus(
  req: Request,
  objectKey: string
): Promise<Buffer> {
  const bucket = getStratusBucket(req);
  const res = await bucket.getObject(objectKey);

  const chunks: Buffer[] = [];
  return new Promise((resolve, reject) => {
    res.on('data', (chunk: Buffer) => chunks.push(chunk));
    res.on('end', () => resolve(Buffer.concat(chunks)));
    res.on('error', reject);
  });
}
