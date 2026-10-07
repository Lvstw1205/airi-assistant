import {collect} from './data.js';import {analyze} from './brain.js';
import {history,grade} from './grading.js';
let input='';for await(const chunk of process.stdin)input+=chunk;
try{const request=JSON.parse(input);let result;if(request.action==='grade'){const bars=await history(request.result.snapshot);result=grade(request.result,bars);}else{const snapshot=request.snapshot||await collect(request.symbol);result=request.action==='analyze'?analyze(snapshot,request.options||{}):{snapshot};}process.stdout.write(JSON.stringify(result));}catch(e){process.stderr.write(e.message);process.exitCode=1;}
