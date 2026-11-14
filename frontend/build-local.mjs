// Portable fallback for Windows sandboxes where parent-directory realpath is denied.
// Standard npm run build remains the primary build on normal Windows/Linux hosts.
import fs from 'node:fs';
import path from 'node:path';
import { transform } from 'esbuild';
import { rollup } from 'rollup';
const root=process.cwd();
const find=(name)=>{
 let p=path.join(root,'node_modules',name);
 if(fs.existsSync(p))return p;
 throw new Error('Missing package '+name);
};
const resolveFile=p=>{
 for(const candidate of [p,p+'.js',p+'.mjs',p+'.tsx',p+'.ts',path.join(p,'index.js')]){
  if(fs.existsSync(candidate)&&fs.statSync(candidate).isFile())return candidate;
 }
 return null;
};
const bundle=await rollup({input:path.join(root,'src/main.tsx'),plugins:[{
 name:'portable-resolver',
 resolveId(source,importer){
  if(source.startsWith('\0'))return source;
  if(path.isAbsolute(source))return source;
  if(source.endsWith('.css'))return '\0css';
  if(source.startsWith('.'))return resolveFile(path.resolve(importer?path.dirname(importer):root,source));
  const parts=source.split('/');const pkg=parts[0].startsWith('@')?parts.slice(0,2).join('/'):parts[0];const dir=find(pkg);const data=JSON.parse(fs.readFileSync(path.join(dir,'package.json'),'utf8'));const sub=source.slice(pkg.length+1);
  if(pkg==='react'||pkg==='react-dom'||pkg==='scheduler')return '\0cjs:'+source;
  return resolveFile(sub?path.join(dir,sub):path.join(dir,data.module||data.main||'index.js'));
 },
 load(id){if(id==='\0css')return '';if(!id.startsWith('\0cjs:'))return null;const name=id.slice(5);const pkg=name.startsWith('react-dom')?'react-dom':name==='scheduler'?'scheduler':'react';const sub=name.slice(pkg.length+1);const file=sub==='jsx-runtime'?'react-jsx-runtime.production.js':sub==='client'?'react-dom-client.production.js':pkg+'.production.js';const source=fs.readFileSync(path.join(find(pkg),'cjs',file),'utf8');
  const requirements=[...new Set([...source.matchAll(/require\(["']([^"']+)["']\)/g)].map(m=>m[1]))];
  return requirements.map((r,i)=>`import * as m${i} from ${JSON.stringify(r)};`).join('\n')+`\nconst exports={};const module={exports};const require=n=>({${requirements.map((r,i)=>`${JSON.stringify(r)}:m${i}.default||m${i}`).join(',')}})[n];\n`+source+'\nexport default module.exports;\n'+(name==='react'?['useState','useEffect','forwardRef','createElement'].map(k=>`export const ${k}=module.exports.${k};`).join('\n'):name==='react-dom/client'?'export const createRoot=module.exports.createRoot;':name==='react/jsx-runtime'?'export const jsx=module.exports.jsx;export const jsxs=module.exports.jsxs;export const Fragment=module.exports.Fragment;':'');
 },
 async transform(code,id){if(id.endsWith('.tsx')||id.endsWith('.ts'))return (await transform(code,{loader:id.endsWith('tsx')?'tsx':'ts',jsx:'automatic',target:'es2022'})).code; if(id.includes('scheduler'))return code;return null;}
 }]});
fs.mkdirSync('dist/assets',{recursive:true});
await bundle.write({file:'dist/assets/app.js',format:'esm',paths:()=> './app.css'});
fs.copyFileSync('src/style.css','dist/assets/app.css');
fs.writeFileSync('dist/index.html','<!doctype html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Destination Tickets</title><link rel="stylesheet" href="/assets/app.css"></head><body><div id="root"></div><script type="module" src="/assets/app.js"></script></body></html>');
console.log('Portable frontend build complete');
