# -*- coding: utf-8 -*-
"""控制台前端模板（与 console.py 分开，改 UI 只动这个文件）。
设计口径：亮色、克制、数字优先；每张卡把「能力 / 速度 / 代价 / 怎么起」写全，免得时间长了忘。"""

PAGE = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>本地模型控制台</title>
<style>
:root{
  --bg:#F5F4F1; --surface:#FFFFFF; --surface2:#FBFAF7; --line:#E6E3DC; --line2:#D8D4CB;
  --ink:#171614; --ink2:#57534B; --ink3:#8B857A;
  --ok:#1A7F4F; --ok-bg:#E8F4ED; --ok-line:#CFE3D6;
  --warn:#8A5206; --warn-bg:#FBF0DF; --warn-line:#F0DFC4;
  --bad:#B03A2E;
  --ease-out:cubic-bezier(0.23,1,0.32,1);
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);font:14px/1.55 "Segoe UI","Microsoft YaHei",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
.page{max-width:1140px;margin:0 auto;padding:30px 22px 60px}

.hd{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding-bottom:18px;
  border-bottom:1px solid var(--line);margin-bottom:22px}
h1{font-size:21px;line-height:1.25;margin:0 0 5px;font-weight:600;letter-spacing:-.01em}
.hd-sub{margin:0;font-size:12.5px;color:var(--ink3)}
.hd-right{display:flex;align-items:center;gap:9px;flex:0 0 auto}
.live{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--ink2);
  background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:5px 11px 5px 10px}
.live i{width:6px;height:6px;border-radius:50%;background:var(--ok);display:block;flex:0 0 auto}
.live.dead i{background:var(--bad)}

.btn{appearance:none;font:inherit;font-size:13px;line-height:1;padding:9px 14px;border-radius:10px;
  border:1px solid var(--line2);background:var(--surface);color:var(--ink);cursor:pointer;
  transition:transform 160ms var(--ease-out),background-color 160ms ease,border-color 160ms ease,color 160ms ease}
.btn:active{transform:scale(.97)}
.btn.primary{background:#1B1A17;border-color:#1B1A17;color:#fff}
.btn.ghost{background:transparent;border-color:transparent;color:var(--ink2);padding:9px 11px}
.btn.danger{color:var(--bad);border-color:#E7D3CF;background:var(--surface)}
.btn.loading::before{content:'';display:inline-block;width:9px;height:9px;margin-right:7px;border-radius:50%;border:1.5px solid currentColor;border-right-color:transparent;animation:spin .7s linear infinite;vertical-align:-1px}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion: reduce){.btn.loading::before{animation:none}}
.btn:disabled{opacity:.45;cursor:default;transform:none}
.btn:focus-visible{outline:2px solid #2A5BD7;outline-offset:2px}
@media (hover:hover) and (pointer:fine){
  .btn:hover{background:var(--surface2);border-color:#BFBAAE}
  .btn.primary:hover{background:#000;border-color:#000}
  .btn.ghost:hover{background:#EDEBE5}
  .btn.danger:hover{background:#FBEAE7;border-color:#DDBCB6}
}

.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px;
  box-shadow:0 1px 2px rgba(23,22,20,.045)}
.sec-label{font-size:11px;font-weight:600;letter-spacing:.09em;color:var(--ink3);margin-bottom:13px}
.grid2{display:grid;grid-template-columns:minmax(0,1.28fr) minmax(0,1fr);gap:14px;align-items:start}

.hero-top{display:flex;align-items:center;gap:10px}
.dot{width:9px;height:9px;border-radius:50%;background:#B7B1A6;flex:0 0 auto}
.dot.ok{background:var(--ok)} .dot.warn{background:#C2740B} .dot.off{background:#B7B1A6}
.hero-title{font-size:19px;font-weight:600;letter-spacing:-.01em;line-height:1.3}
.mono{font-family:"Cascadia Mono",Consolas,ui-monospace,monospace;font-size:11.5px}
.muted{color:var(--ink3)}
.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:16px 0 15px}
.m{background:var(--surface2);border:1px solid #EFEDE7;border-radius:11px;padding:10px 12px;min-width:0}
.ml{display:block;font-size:11px;color:var(--ink3);margin-bottom:4px}
.mv{font-size:16px;font-weight:600;letter-spacing:-.01em;line-height:1.25;display:block}
.ms{display:block;font-size:11px;color:var(--ink3);margin-top:3px;line-height:1.4}
.hero-acts{display:flex;flex-wrap:wrap;gap:8px}
.hint{margin:12px 0 0;font-size:12.5px;color:var(--ink3);line-height:1.6}

.track{height:8px;background:#EDEBE5;border-radius:99px;overflow:hidden;margin:10px 0 6px}
.track > i{display:block;height:100%;background:#1B1A17;border-radius:99px;
  transition:width 260ms var(--ease-out),background-color 200ms ease}
.track > i.warn{background:#C2740B}
.track > i.bad{background:var(--bad)}
.bignum{font-size:16px;font-weight:600}
.stat3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:14px;font-size:12px;color:var(--ink2)}
.stat3 div{background:var(--surface2);border:1px solid #EFEDE7;border-radius:9px;padding:7px 10px}
.stat3 b{display:block;color:var(--ink);font-weight:600;font-size:13px;margin-top:1px}
.ports{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.port{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;color:var(--ink2);
  background:var(--surface2);border:1px solid #EFEDE7;border-radius:999px;padding:3px 9px}
.port i{width:5px;height:5px;border-radius:50%;background:#CFCBC2;display:block}
.port.on{color:#166B43;background:var(--ok-bg);border-color:var(--ok-line)}
.port.on i{background:var(--ok)}
.proclist{margin:12px 0 0;padding:0;list-style:none;font-size:11.5px;color:var(--ink3);display:grid;gap:3px}

.sec{margin-top:26px}
.sec-head{margin-bottom:14px}
.sec-head h2{font-size:15.5px;margin:0 0 5px;font-weight:600;letter-spacing:-.01em}
.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
@media (max-width:900px){.cards{grid-template-columns:1fr}.grid2{grid-template-columns:1fr}.metrics{grid-template-columns:1fr 1fr}}

.pcard{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:18px 18px 15px;box-shadow:0 1px 2px rgba(23,22,20,.045);
  transition:border-color 160ms ease,box-shadow 160ms ease}
.pcard[data-state="ready"]{border-color:var(--ok-line);
  box-shadow:0 1px 2px rgba(23,22,20,.045),inset 2px 0 0 var(--ok)}
.pcard[data-state="half"]{box-shadow:0 1px 2px rgba(23,22,20,.045),inset 2px 0 0 #C2740B}
.phead{display:flex;align-items:flex-start;gap:10px}
.pno{font-family:"Cascadia Mono",Consolas,monospace;font-size:11px;color:var(--ink3);
  border:1px solid var(--line);border-radius:6px;padding:2px 5px;line-height:1.35;flex:0 0 auto;margin-top:2px}
.ptitle{min-width:0;flex:1}
.ptitle h3{font-size:15px;margin:0;font-weight:600;letter-spacing:-.01em;line-height:1.35}
.psub{display:block;font-size:11.5px;color:var(--ink3);margin-top:2px}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;border-radius:999px;
  padding:3px 9px;border:1px solid transparent;white-space:nowrap;flex:0 0 auto}
.chip i{width:5px;height:5px;border-radius:50%;background:currentColor;display:block}
.chip.ready{color:#166B43;background:var(--ok-bg);border-color:var(--ok-line)}
.chip.switch,.chip.half{color:var(--warn);background:var(--warn-bg);border-color:var(--warn-line)}
.tagline{font-size:13px;color:var(--ink2);margin:10px 0 0;line-height:1.6}
.ctx{display:flex;align-items:center;gap:10px;margin:14px 0 0}
.ctx .track{flex:1;margin:0}
.ctx span{font-size:11px;color:var(--ink3);flex:0 0 auto}
.specs{display:grid;grid-template-columns:58px minmax(0,1fr);gap:7px 12px;margin:14px 0 0;
  padding-top:13px;border-top:1px solid #EFEDE7}
.specs dt{font-size:11.5px;color:var(--ink3);padding-top:1px}
.specs dd{margin:0;font-size:12.5px;color:#47433C;line-height:1.5}
.specs dd b{color:var(--ink);font-weight:600}
.why{list-style:none;margin:13px 0 14px;padding:0;display:grid;gap:6px}
.why li{font-size:12.5px;line-height:1.55;color:var(--ink2);padding-left:17px;position:relative}
.why li::before{position:absolute;left:0;top:-1px;font-size:13px;font-weight:700}
.why li.yes::before{content:"\2713";color:var(--ok)}
.why li.no::before{content:"\00d7";color:var(--bad)}
.pcard{display:flex;flex-direction:column}
.grid2 .card{display:flex;flex-direction:column}
.tip{margin-top:auto;padding-top:13px;border-top:1px dashed var(--line);font-size:11.5px;color:var(--ink3);line-height:1.65}
.pfoot{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-top:auto;padding-top:14px;
  border-top:1px dashed var(--line)}
.dsh{font-size:11px;color:var(--ink3);display:flex;align-items:center;gap:5px;min-width:0;flex:1}
code{font-family:"Cascadia Mono",Consolas,ui-monospace,monospace;font-size:11px;background:#F3F1EC;
  border:1px solid #EAE7E0;border-radius:5px;padding:1px 5px;color:#47433C;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}

.strip{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2);
  background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:10px 14px;margin-top:14px;
  box-shadow:0 1px 2px rgba(23,22,20,.03)}
.strip b{font-weight:600;color:var(--ink)}

@media (hover:hover) and (pointer:fine){.pcard:hover{border-color:var(--line2)}}
details.logs{margin-top:26px;padding:0}
details.logs summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:9px;
  padding:15px 18px;font-size:13px;font-weight:600}
details.logs summary::-webkit-details-marker{display:none}
details.logs summary .muted{font-weight:400;font-size:12px}
.caret{width:12px;height:12px;flex:0 0 auto;color:var(--ink3);transition:transform 180ms var(--ease-out)}
details[open] .caret{transform:rotate(90deg)}
.logbody{padding:0 18px 16px}
select{font:inherit;font-size:12.5px;padding:7px 10px;border-radius:9px;border:1px solid var(--line2);
  background:var(--surface);color:var(--ink);margin-bottom:10px}
pre{margin:0;background:var(--surface2);border:1px solid #EAE7E0;border-radius:10px;padding:12px;
  height:210px;overflow:auto;font:11.5px/1.5 "Cascadia Mono",Consolas,monospace;white-space:pre-wrap;
  color:#47433C;word-break:break-all}
.foot{margin:22px 0 0;font-size:11.5px;color:var(--ink3);line-height:1.75}
.foot code{font-size:10.5px}

.toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,10px);background:#1B1A17;color:#fff;
  font-size:13px;padding:11px 16px;border-radius:11px;box-shadow:0 10px 30px rgba(23,22,20,.24);
  opacity:0;pointer-events:none;max-width:min(600px,calc(100vw - 32px));line-height:1.5;
  transition:opacity 180ms var(--ease-out),transform 180ms var(--ease-out)}
.toast.show{opacity:1;transform:translate(-50%,0)}
@media (prefers-reduced-motion:reduce){
  .btn:active{transform:none}
  .track > i{transition:none}
  .toast{transition:opacity 120ms linear;transform:translate(-50%,0)}
  .caret{transition:none}
}
</style></head><body>
<div class="page">

  <header class="hd">
    <div>
      <h1>本地模型控制台</h1>
      <p class="hd-sub">RTX 4060 Ti 8G · 一张卡同一时刻只能跑一个引擎 · 下面每个数字都是这台机器上实测的</p>
    </div>
    <div class="hd-right">
      <span class="live" id="live"><i></i><span id="liveness">连接中</span></span>
      <button class="btn ghost" data-action="refresh">立即刷新</button>
    </div>
  </header>

  <section class="grid2">
    <div class="card">
      <div class="sec-label">当前正在跑</div>
      <div class="hero-top">
        <span class="dot off" id="hero-dot"></span>
        <div style="min-width:0">
          <div class="hero-title" id="hero-name">读状态中</div>
          <div class="mono muted" id="hero-id" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">—</div>
        </div>
      </div>
      <div class="metrics">
        <div class="m"><span class="ml">窗口 / 上下文</span><span class="mv" id="m-ctx">—</span><span class="ms" id="m-ctxs">&nbsp;</span></div>
        <div class="m"><span class="ml">生成速度</span><span class="mv" id="m-speed">—</span><span class="ms" id="m-speeds">&nbsp;</span></div>
        <div class="m"><span class="ml">首字延迟</span><span class="mv" id="m-ttft">—</span><span class="ms" id="m-ttfts">&nbsp;</span></div>
      </div>
      <div class="hero-acts" id="hero-acts"></div>
      <p class="hint" id="hero-hint">上面就是现在能用的那一档；右边三个按钮＝直接换档，约 10–25 秒。</p>
    </div>

    <div class="card">
      <div class="sec-label">显存与系统</div>
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px">
        <span class="bignum"><span id="vram">—</span> <span class="muted" style="font-weight:400;font-size:12px">MiB</span></span>
        <span class="mono muted" id="vrampct">—</span>
      </div>
      <div class="track"><i id="vrambar" style="width:0%"></i></div>
      <div class="stat3">
        <div>利用率<b id="s-util">—</b></div>
        <div>温度<b id="s-temp">—</b></div>
        <div>功耗<b id="s-power">—</b></div>
      </div>
      <div class="ports" id="ports"></div>
      <ul class="proclist" id="proclist"></ul>
      <div class="tip">换档＝停旧起新，约 10–25 秒；这期间 DSH 里对应那条会返回 502，起完就恢复。显存超过 92% 时先关掉别的吃显存的程序（OBS、游戏、浏览器硬件加速）。</div>
    </div>
  </section>

  <div class="strip" id="strip"></div>

  <section class="sec">
    <div class="sec-head">
      <h2>四条路 · 各是什么能力、什么速度</h2>
      <p class="hint">问答/写代码用 01；想让它一次读完几万字用 02；要它自己通读 15 万字用 03；超长文只要答案、还要快用 04。左边绿条＝现在就能用。</p>
    </div>
    <div class="cards" id="cards"></div>
  </section>

  <details class="card logs">
    <summary>
      <svg class="caret" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4.5 2.5 8 6l-3.5 3.5"/></svg>
      日志尾巴 <span class="muted">起服 / 代理的原始输出，出问题时先看这里</span>
    </summary>
    <div class="logbody">
      <select id="logsel" onchange="loadLog()"></select>
      <pre id="logtext">（选一个日志）</pre>
    </div>
  </details>

  <p class="foot">
    读数出处：<code>reports/上下文-150K-200K-实测-20261030.md</code>（上下文上限 / 分片 / llama 单遍）、
    <code>reports/实测-40k档-20261030.md</code>（40K 档速度）、<code>docs/上下文手册-20261030.md</code>（用法与代价）。
    全部是这台 4060 Ti 8G + 这份 PTQ1 模型测出来的；换机器、换模型这些数都不作数。
  </p>
</div>
<div class="toast" id="toast"></div>
<script>
var RUNNING = null, PROFS = [], TIMER = null, PENDING = null;

function esc(s){
  var m = {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"};
  return String(s==null?"":s).replace(/[&<>"]/g, function(c){ return m[c]; });
}
function nfmt(n){ return n==null? "—" : String(n).replace(/\B(?=(\d{3})+(?!\d))/g,","); }
function p2(x){ return (x<10?"0":"")+x; }
function clock(ts){ if(!ts) return "—"; var d=new Date(ts*1000); return p2(d.getHours())+":"+p2(d.getMinutes())+":"+p2(d.getSeconds()); }

function byKey(k){ for(var i=0;i<PROFS.length;i++){ if(PROFS[i].key===k) return PROFS[i]; } return null; }

var PENDING = null;
var ACTNAME = {'engine:40k':'切到 40K','engine:72k':'切到 72K','engine:llama':'起 llama 262K','engine:stop':'停掉引擎','proxy:start':'起分片代理','proxy:stop':'停分片代理'};
function pendAct(a){ return ACTNAME[a] || a; }
function pendDone(a){
  if(a==='engine:40k') return RUNNING==='p40';
  if(a==='engine:72k') return RUNNING==='p72';
  if(a==='engine:llama') return RUNNING==='llama';
  if(a==='engine:stop') return !RUNNING;
  var s = byKey('shard');
  if(a==='proxy:start') return !!(s && s.state==='ready');
  if(a==='proxy:stop') return !!(s && s.state!=='ready');
  return false;
}

function renderHero(){
  var p = RUNNING ? byKey(RUNNING) : null;
  var dot = document.getElementById('hero-dot');
  var name = document.getElementById('hero-name');
  var hid  = document.getElementById('hero-id');
  var hint = document.getElementById('hero-hint');
  if(p){
    dot.className = 'dot ok';
    name.textContent = p.name;
    hid.textContent = p.dsh;
    document.getElementById('m-ctx').textContent   = nfmt(p.ctx);
    document.getElementById('m-ctxs').textContent  = p.ctxnote;
    document.getElementById('m-speed').textContent = (p.speedunit==="整篇" ? p.speed : p.speed+" "+p.speedunit);
    document.getElementById('m-speeds').textContent= p.speednote;
    document.getElementById('m-ttft').textContent  = p.ttft;
    document.getElementById('m-ttfts').textContent = p.ttftnote;
    hint.textContent = p.headline + "。在 DSH 里选「" + p.dsh + "」。";
  }else{
    dot.className = 'dot off';
    name.textContent = '引擎没起';
    hid.textContent = '点下面任一按钮起一档；起完 DSH 里对应的那条就亮了';
    ['m-ctx','m-speed','m-ttft'].forEach(function(id){ document.getElementById(id).textContent='—'; });
    ['m-ctxs','m-speeds','m-ttfts'].forEach(function(id){ document.getElementById(id).textContent='\u00a0'; });
    hint.textContent = '一张卡同一时刻只能跑一个引擎，所以这里只显示一档。要换用途就换档。';
  }
  var acts = [
    ['engine:40k','切到 40K','p40'],
    ['engine:72k','切到 72K','p72'],
    ['engine:llama','起 llama 262K','llama']
  ];
  var html = '';
  for(var i=0;i<acts.length;i++){
    var cur = RUNNING === acts[i][2];
    var pend = !!(PENDING && PENDING.a === acts[i][0]);
    html += '<button class="btn ' + (cur || pend ? '' : 'primary') + (pend ? ' loading' : '') + '" data-action="' + acts[i][0] + '"' +
            (cur || pend ? ' disabled' : '') + '>' + (pend ? '正在起…' : (cur ? '正在用' : acts[i][1])) + '</button>';
  }
  var pstop = !!(PENDING && PENDING.a === 'engine:stop');
  html += '<button class="btn danger' + (pstop ? ' loading' : '') + '" data-action="engine:stop"' + (pstop ? ' disabled' : '') + '>' + (pstop ? '正在停…' : '停掉引擎') + '</button>';
  document.getElementById('hero-acts').innerHTML = html;
}

function cardHTML(p){
  var chipText = p.state==='ready' ? '就绪' : (p.state==='half' ? '差一步' : '要换档');
  var pend = !!(PENDING && PENDING.a === p.action);
  var btnLabel = pend ? (p.action==='proxy:stop' ? '正在停…' : '正在起…') : (p.state==='ready' ? '正在用' : (p.action==='proxy:start' ? '起分片代理' : '切到这一档'));
  var btnDisabled = p.state==='ready' || pend;
  var pct = Math.max(2, Math.min(100, 100*p.ctx/262144));
  var speedText = (p.speedunit==='整篇') ? p.speed : (p.speed + ' ' + p.speedunit);
  var h = [];
  h.push('<article class="pcard" data-state="' + esc(p.state) + '">');
  h.push('  <div class="phead">');
  h.push('    <span class="pno">' + esc(p.idx) + '</span>');
  h.push('    <div class="ptitle"><h3>' + esc(p.name) + '</h3><span class="psub">' + esc(p.sub) + '</span></div>');
  h.push('    <span class="chip ' + esc(p.state) + '"><i></i>' + chipText + '</span>');
  h.push('  </div>');
  h.push('  <p class="tagline">' + esc(p.headline) + '</p>');
  h.push('  <div class="ctx"><div class="track"><i style="width:' + pct.toFixed(1) + '%"></i></div><span>' + nfmt(p.ctx) + '</span></div>');
  h.push('  <dl class="specs">');
  h.push('    <dt>上下文</dt><dd><b>' + nfmt(p.ctx) + '</b> · ' + esc(p.ctxnote) + '</dd>');
  h.push('    <dt>生成</dt><dd><b>' + esc(speedText) + '</b> · ' + esc(p.speednote) + '</dd>');
  h.push('    <dt>首字</dt><dd><b>' + esc(p.ttft) + '</b> · ' + esc(p.ttftnote) + '</dd>');
  h.push('    <dt>显存</dt><dd><b>' + esc(p.vram) + '</b></dd>');
  h.push('    <dt>怎么起</dt><dd>' + esc(p.need) + '</dd>');
  if(p.cost){ h.push('    <dt>代价</dt><dd style="color:#6B655C">' + esc(p.cost) + '</dd>'); }
  h.push('  </dl>');
  h.push('  <ul class="why"><li class="yes">' + esc(p.yes) + '</li><li class="no">' + esc(p.avoid) + '</li></ul>');
  h.push('  <div class="pfoot">');
  h.push('    <button class="btn ' + (btnDisabled ? '' : 'primary') + (pend ? ' loading' : '') + '" data-action="' + esc(p.action) + '"' + (btnDisabled ? ' disabled' : '') + '>' + btnLabel + '</button>');
  h.push('    <span class="dsh">DSH 选 <code>' + esc(p.dsh) + '</code></span>');
  h.push('  </div>');
  if(p.state!=='ready' && p.why){ h.push('  <p class="hint" style="margin:9px 0 0;font-size:11.5px">现在还不能用：' + esc(p.why) + '</p>'); }
  h.push('</article>');
  return h.join('\n');
}

function renderCards(){ document.getElementById('cards').innerHTML = PROFS.map(cardHTML).join('\n'); }

function renderSys(d){
  var g = d.gpu || {};
  var used = g.used, total = g.total;
  document.getElementById('vram').textContent = (used==null? '—' : used) + ' / ' + (total==null? '—' : total);
  var pct = (used!=null && total) ? 100*used/total : 0;
  var bar = document.getElementById('vrambar');
  bar.style.width = pct.toFixed(1) + '%';
  bar.className = pct > 92 ? 'bad' : (pct > 84 ? 'warn' : '');
  document.getElementById('vrampct').textContent = pct ? pct.toFixed(1) + '% 已用' : '—';
  document.getElementById('s-util').textContent = (g.util==null?'—':g.util+' %');
  document.getElementById('s-temp').textContent = (g.temp==null?'—':g.temp+' °C');
  document.getElementById('s-power').textContent = (g.power==null?'—':Math.round(g.power)+' W');

  var ports = [
    ['引擎 8091', d.engine.open],
    ['网关 8081', d.gateway.open],
    ['分片代理 8086', d.proxy.open],
    ['llama 8089', d.llama.open]
  ];
  var ph = '';
  for(var i=0;i<ports.length;i++){
    ph += '<span class="port ' + (ports[i][1] ? 'on' : '') + '"><i></i>' + ports[i][0] + '</span>';
  }
  document.getElementById('ports').innerHTML = ph;

  var pl = '';
  if(d.procs && d.procs.length){
    for(var j=0;j<d.procs.length;j++){
      var q = d.procs[j];
      pl += '<li>' + esc(q.name) + ' · pid ' + esc(q.pid) + ' · ' + nfmt(q.mib) + ' MiB 内存</li>';
    }
  }else{
    pl = '<li>没有本地引擎进程</li>';
  }
  document.getElementById('proclist').innerHTML = pl;
}

function renderStrip(d){
  var s = '';
  var last = d.last || {};
  if(PENDING){
    s += '<span>正在执行：<b>' + esc(pendAct(PENDING.a)) + '</b> · 已等 ' + Math.round((Date.now()-PENDING.ts)/1000) + ' 秒 · 起服约 10–25 秒</span>';
  }else if(last.at){ s += '<span>上次动作：<b>' + esc(last.label) + '</b> · ' + clock(last.at) + (last.log ? ' · 日志 ' + esc(last.log) : '') + '</span>'; }
  else { s += '<span>还没从这里按过按钮。</span>'; }
  s += '<span style="margin-left:auto" class="muted">状态刷新于 ' + clock(d.ts) + '，每 2 秒一次</span>';
  document.getElementById('strip').innerHTML = s;
}

async function refresh(){
  try{
    var r = await fetch('/api/status');
    var d = await r.json();
    RUNNING = d.running; PROFS = d.profiles || []; window.LAST = d.last || {}; window.STATUS = d;
    if(PENDING && (pendDone(PENDING.a) || Date.now() - PENDING.ts > 180000)) PENDING = null;
    document.getElementById('live').className = 'live';
    document.getElementById('liveness').textContent = '运行中';
    renderHero(); renderCards(); renderSys(d); renderStrip(d);
    var sel = document.getElementById('logsel');
    if(!sel.options.length && d.logs){
      for(var i=0;i<d.logs.length;i++){
        var o = document.createElement('option'); o.value = d.logs[i]; o.textContent = d.logs[i];
        sel.appendChild(o);
      }
    }
    if(document.querySelector('details.logs').open) loadLog();
  }catch(e){
    document.getElementById('live').className = 'live dead';
    document.getElementById('liveness').textContent = '控制台断开';
  }
}

async function act(action){
  if(action === 'refresh'){ refresh(); return; }
  var btn = document.querySelector('[data-action="' + action + '"]');
  if(btn && btn.disabled) return;
  if(btn){ btn.disabled = true; }
  PENDING = {a: action, ts: Date.now()};
  renderHero(); renderCards(); renderStrip(window.STATUS || {last:(window.LAST||{})});
  try{
    var r = await fetch('/api/action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action: action})});
    var j = await r.json();
    if(j.ok){
      var msg = '已触发：' + (j.label || action);
      if(j.action && j.action.indexOf('engine:') === 0){ msg += '；正在起服，约 10–25 秒，起来后这里会自动变绿'; }
      if(j.log){ msg += ' · 日志 ' + j.log; }
      toast(msg);
    }else{
      toast('失败：' + (j.error || '未知错误'));
    }
  }catch(e){
    toast('请求失败：' + e);
  }
  setTimeout(refresh, 1200);
}

var TOAST_T = null;
function toast(msg){
  var t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(TOAST_T);
  TOAST_T = setTimeout(function(){ t.classList.remove('show'); }, 4200);
}

async function loadLog(){
  var sel = document.getElementById('logsel');
  if(!sel.value) return;
  try{
    var d = await (await fetch('/api/log?f=' + encodeURIComponent(sel.value))).json();
    var el = document.getElementById('logtext');
    el.textContent = d.tail || '(空)';
    el.scrollTop = el.scrollHeight;
  }catch(e){}
}

document.addEventListener('click', function(e){
  var t = e.target.closest ? e.target.closest('[data-action]') : null;
  if(!t || t.disabled) return;
  act(t.getAttribute('data-action'));
});
document.querySelector('details.logs').addEventListener('toggle', function(){ if(this.open) loadLog(); });
refresh();
TIMER = setInterval(refresh, 2000);
</script></body></html>"""
