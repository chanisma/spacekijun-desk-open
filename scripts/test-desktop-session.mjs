import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const source = await readFile('C:/repository/spacekijun/supabase/functions/desktop-session/handler.js','utf8');
const {createHandler} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const env = {url:'https://project.test',anonKey:'public-test',serviceKey:'server-test'};
let calls=[], unauthorized=false, mfa=false, mismatch=false;
const fetcher=async(url, options)=>{
  calls.push({url,options});
  if(url.endsWith('/user')) return Response.json({id:'caller',email:'verified@example.test',email_confirmed_at:'2026-09-11',factors:mfa?[{status:'verified'}]:[]},{status:unauthorized?401:200});
  if(url.endsWith('/admin/generate_link')) {
    assert.deepEqual(JSON.parse(options.body),{type:'magiclink',email:'verified@example.test'});
    return Response.json({id:mismatch?'another-user':'caller',hashed_token:'one-use-test'});
  }
  if(url.endsWith('/verify')) return Response.json({access_token:'new-session',refresh_token:'independent-refresh',user:{id:'caller'}});
  throw Error('Unexpected API call');
};
const handler=createHandler(env,fetcher);
const req=(body={site:'space'}, headers={Authorization:'Bearer desktop-test'})=>new Request('https://function.test',{method:'POST',headers,body:JSON.stringify(body)});
assert.equal((await handler(req({},{}))).status,401);assert.equal(calls.length,0);
assert.equal((await handler(req({site:'space',email:'someone-else@test'}))).status,400);assert.equal(calls.length,0);
assert.equal((await handler(req({site:'space'},{Authorization:'Bearer desktop-test',Origin:'https://evil.test'}))).status,403);
unauthorized=true;assert.equal((await handler(req())).status,401);assert.equal(calls.length,1);
unauthorized=false;mfa=true;calls=[];assert.equal((await handler(req())).status,403);assert.equal(calls.length,1);
mfa=false;mismatch=true;calls=[];assert.equal((await handler(req())).status,502);assert.equal(calls.length,2);
mismatch=false;calls=[];const result=await handler(req({site:'seaton'}));assert.equal(result.status,200);
assert.equal((await result.json()).session.user.id,'caller');assert.equal(calls.length,3);
assert.equal(result.headers.get('Cache-Control'),'no-store');
console.log('PASS: verified caller only, no arbitrary identity, no browser CORS, MFA guard, independent session');
