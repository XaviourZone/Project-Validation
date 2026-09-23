let sourceData=null;

async function api(path, options={}) {
  const r=await fetch(path,{cache:"no-store",headers:{"Content-Type":"application/json"},...options});
  const d=await r.json();
  if(!r.ok) throw new Error(d.error||d.message||"Request failed");
  return d;
}
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function msg(v){document.getElementById("message").textContent=v;}
function serviceState(x){return x?.health?.reachable?"RUNNING":"STOPPED";}
function renderSource(s){
  const c=s.config||{};
  const common='<div class="row"><label>Enabled</label><input type="checkbox" data-k="enabled" '+(s.enabled?"checked":"")+'></div>'+
    '<div class="row"><label>Parser</label><select data-k="parser">'+Object.keys(sourceData.parser_destinations||{}).map(x=>'<option '+(x===s.parser?"selected":"")+'>'+esc(x)+'</option>').join("")+'</select></div>';
  let specific="";
  if(s.type==="file"){
    specific=
      '<div class="row"><label>Folder</label><input class="wide" data-k="folder" value="'+esc(s.folder)+'"><button onclick="browse(\''+esc(s.name)+'\')">BROWSE</button></div>'+
      '<div class="row"><label>File patterns</label><input class="wide" data-k="file_patterns" value="'+esc((s.patterns||[]).join(", "))+'"></div>'+
      '<div class="row"><label>Poll seconds</label><input type="number" step="0.1" data-k="poll_interval_seconds" value="'+esc(s.poll_interval_seconds)+'"><label>Stability</label><input type="number" step="0.1" data-k="stability_window_seconds" value="'+esc(s.stability_window_seconds)+'"></div>'+
      '<div class="row"><label>Preserve file</label><input type="checkbox" data-k="preserve_file" '+(s.preserve_file?"checked":"")+'><label>Processed folder</label><input class="wide" data-k="processed_folder" value="'+esc(s.processed_folder)+'"></div>';
  }else{
    specific=
      '<div class="row"><label>Remote host</label><input class="wide" data-k="remote_host" value="'+esc(s.host)+'"><label>Port</label><input type="number" data-k="remote_port" value="'+esc(s.port)+'"></div>'+
      '<div class="row"><label>Framing</label><select data-k="framing"><option '+(s.framing==="line"?"selected":"")+' value="line">LINE</option><option '+(s.framing==="length_prefixed"?"selected":"")+' value="length_prefixed">LENGTH PREFIXED</option><option '+(s.framing==="raw_block"?"selected":"")+' value="raw_block">RAW BLOCK</option></select><label>Delimiter</label><input data-k="delimiter" value="'+esc(s.delimiter)+'"></div>'+
      '<div class="row"><label>Max bytes</label><input type="number" data-k="max_line_length" value="'+esc(s.max_line_length)+'"><label>Reconnect initial</label><input type="number" step="0.1" data-k="reconnect_initial_delay" value="'+esc(s.reconnect_initial_delay)+'"></div>'+
      '<div class="row"><label>Reconnect max</label><input type="number" step="0.1" data-k="reconnect_max_delay" value="'+esc(s.reconnect_max_delay)+'"><label>Multiplier</label><input type="number" step="0.1" data-k="reconnect_multiplier" value="'+esc(s.reconnect_multiplier)+'"></div>';
  }
  return '<article class="source '+(s.enabled?"enabled":"disabled")+'"><header><div><span class="type">'+esc(s.type.toUpperCase())+'</span><h3>'+esc(s.name)+'</h3></div><span class="badge '+(s.enabled?"on":"off")+'">'+(s.enabled?"ENABLED":"DISABLED")+'</span></header><div class="form">'+common+specific+'</div><div class="actions"><button onclick="applySource(\''+esc(s.name)+'\')">APPLY</button><span class="pathstate">'+(s.type==="file"?(s.exists?"FOLDER OK":"FOLDER MISSING"):(s.host+":"+s.port))+'</span></div></article>';
}
async function loadSources(){
  sourceData=await api("/api/router/sources");
  document.getElementById("sources").innerHTML=(sourceData.sources||[]).map(renderSource).join("");
  document.getElementById("router-summary").textContent=(sourceData.sources||[]).length+" configured sources · "+Object.keys(sourceData.parser_destinations||{}).length+" parser destinations · "+sourceData.base_dir;
}
function sourceCard(name){return [...document.querySelectorAll(".source")].find(x=>x.querySelector("h3")?.textContent===name);}
function val(card,k){
  const e=card.querySelector('[data-k="'+k+'"]');
  if(e.type==="checkbox") return e.checked;
  return e.value;
}
async function applySource(name){
  const card=sourceCard(name); const s=sourceData.sources.find(x=>x.name===name);
  const body={name};
  ["enabled","parser"].forEach(k=>body[k]=val(card,k));
  if(s.type==="file"){
    body.folder=val(card,"folder");
    body.file_patterns=val(card,"file_patterns").split(",").map(x=>x.trim()).filter(Boolean);
    body.poll_interval_seconds=Number(val(card,"poll_interval_seconds"));
    body.stability_window_seconds=Number(val(card,"stability_window_seconds"));
    body.preserve_file=val(card,"preserve_file");
    body.processed_folder=val(card,"processed_folder");
  }else{
    ["remote_host","remote_port","framing","delimiter","max_line_length","reconnect_initial_delay","reconnect_max_delay","reconnect_multiplier"].forEach(k=>body[k]=val(card,k));
  }
  try{
    await api("/api/router/source",{method:"POST",body:JSON.stringify(body)});
    msg(name+" configuration saved. Restart Router to apply.");
    await loadSources();
  }catch(e){msg(e.message);}
}
async function browse(name){
  try{
    const r=await api("/api/router/browse");
    if(r.success){sourceCard(name).querySelector('[data-k="folder"]').value=r.path;}
    msg(r.message);
  }catch(e){msg(e.message);}
}
async function serviceAction(name,action){
  try{await api("/api/service/"+name+"/"+action,{method:"POST",body:"{}"});msg(name.toUpperCase()+" "+action.toUpperCase()+" requested");setTimeout(refresh,500);}
  catch(e){msg(e.message);}
}
async function refresh(){
  try{
    const d=await api("/api/status");
    for(const n of ["router","parser","forwarder"]){
      const e=document.getElementById(n+"-state"); const st=serviceState(d.services[n]);
      e.textContent=st; e.className="state "+(st==="RUNNING"?"good":"");
    }
    document.getElementById("clock").textContent=d.time.split(" ")[1]||d.time;
    document.getElementById("router-status").textContent=JSON.stringify(d.router,null,2);
    await loadSources();
  }catch(e){msg(e.message);}
}
setInterval(refresh,3000); refresh();