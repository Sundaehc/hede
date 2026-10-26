import { fileURLToPath } from "node:url"
import { nextBuild } from "../../frontend/node_modules/next/dist/cli/next-build.js"

process.env.NEXT_DIST_DIR = ".next-product-copy-20261026"

await nextBuild(
  { turbopack: true, mangling: true, experimentalBuildMode: "default" },
  fileURLToPath(new URL("../../frontend/", import.meta.url))
)
