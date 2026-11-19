import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const babelParser = require("@babel/parser");
const babelTraverse = require("@babel/traverse").default;
const babelGenerator = require("@babel/generator").default;

function localizeStaticJsx() {
  const translatedAttributes = new Set(["aria-label", "alt", "placeholder", "title"]);
  const sourcePattern = /\/src\/(?:App|AdminPanel)\.jsx$/;

  return {
    name: "localize-static-jsx",
    enforce: "pre",
    transform(source, id) {
      if (!sourcePattern.test(id)) return null;
      const ast = babelParser.parse(source, {
        sourceType: "module",
        plugins: ["jsx"],
      });
      let changed = false;

      babelTraverse(ast, {
        JSXText(path) {
          if (!path.node.value.trim()) return;
          path.replaceWith({
            type: "JSXExpressionContainer",
            expression: {
              type: "CallExpression",
              callee: { type: "Identifier", name: "t" },
              arguments: [{ type: "StringLiteral", value: path.node.value }],
            },
          });
          changed = true;
        },
        JSXAttribute(path) {
          if (!translatedAttributes.has(path.node.name.name)) return;
          if (path.node.value?.type !== "StringLiteral") return;
          path.node.value = {
            type: "JSXExpressionContainer",
            expression: {
              type: "CallExpression",
              callee: { type: "Identifier", name: "t" },
              arguments: [{ type: "StringLiteral", value: path.node.value.value }],
            },
          };
          changed = true;
        },
      });

      if (!changed) return null;
      const hasTranslator = ast.program.body.some((node) =>
        node.type === "ImportDeclaration"
        && node.source.value === "./i18n.js"
        && node.specifiers.some((specifier) => specifier.local?.name === "t"),
      );
      if (!hasTranslator) {
        ast.program.body.unshift({
          type: "ImportDeclaration",
          specifiers: [{
            type: "ImportSpecifier",
            imported: { type: "Identifier", name: "t" },
            local: { type: "Identifier", name: "t" },
          }],
          source: { type: "StringLiteral", value: "./i18n.js" },
        });
      }
      return {
        code: babelGenerator(ast, { retainLines: true }, source).code,
        map: null,
      };
    },
  };
}

export default defineConfig({
  plugins: [localizeStaticJsx(), react()],
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": "http://127.0.0.1:5000",
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/three/")) return "three";
          if (id.includes("/node_modules/@react-three/fiber/")) return "react-three-fiber";
          if (id.includes("/node_modules/@react-three/drei/")) return "react-three-drei";
        },
      },
    },
  },
});
