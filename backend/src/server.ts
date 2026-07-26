import dotenv from "dotenv";
dotenv.config();

import { createApp } from "./app";

// When deployed as a Catalyst AppSail service, Catalyst injects the port
// your app must listen on via X_ZOHO_CATALYST_LISTEN_PORT - it will not
// respect PORT in that environment. PORT still works for local dev.
const PORT =
  Number(process.env.X_ZOHO_CATALYST_LISTEN_PORT) ||
  Number(process.env.PORT) ||
  4000;
const app = createApp();

app.listen(PORT, () => {
  console.log(`FIR backend prototype listening on http://localhost:${PORT}`);
  console.log(`API root: http://localhost:${PORT}/api`);
});
