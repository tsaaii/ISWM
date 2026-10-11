/* ISWM plant app — screens.
 * A port of the Claude Design prototype "ISWM Plant App.dc.html": same layout,
 * styles and support codes, wired to the Python side through /api calls. */
(function () {
'use strict';
const h = htm.bind(React.createElement);
const DS = window.TharuniAssociatesDesignSystem_ce9184;
const { Button, Input, Checkbox, Dialog } = DS;

// --- plumbing --------------------------------------------------------------
const TOKEN = new URLSearchParams(location.hash.slice(1)).get('t') || '';
async function api(name, args) {
  const r = await fetch('/api/' + name, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-ISWM-Token': TOKEN}, body: JSON.stringify(args || {})});
  let j;
  try { j = await r.json(); } catch (e) { throw new Error('No answer from the app. Restart it.'); }
  if (!j.ok) throw new Error(j.error || 'Something went wrong.');
  return j.data;
}
const camUrl = name => '/cam/' + name + '.mjpg?t=' + encodeURIComponent(TOKEN);

// The prototype writes styles as CSS strings; React wants objects.
const cssCache = new Map();
function css(str) {
  let o = cssCache.get(str);
  if (o) return o;
  o = {};
  str.split(';').forEach(decl => {
    const i = decl.indexOf(':');
    if (i < 0) return;
    const k = decl.slice(0, i).trim(), v = decl.slice(i + 1).trim();
    if (!k) return;
    o[k.startsWith('--') ? k : k.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
  });
  if (cssCache.size > 4000) cssCache.clear();
  cssCache.set(str, o);
  return o;
}

// --- constants from the prototype ----------------------------------------------
const C = {1:'#1B8A3A',2:'#1D5FC2',3:'#7B4A1F',4:'#F2C200',5:'#151515',6:'#E0620B'};
const FG = {1:'#fff',2:'#fff',3:'#fff',4:'#151515',5:'#fff',6:'#fff'};
const RED = '#C62828', YEL = '#F2C200', GRN = '#1B8A3A';
const IN_TYPES = ['Mixed','Wet','Dry'];
const MATERIALS = ['Compost','RDF bales','Recyclables','Non recyclables','Metal scrap','Glass scrap','Disposal'];
const RECYC = [['pet','PET'],['hdpe','HDPE'],['ldpe','LDPE film'],['paper','Paper and cardboard'],['metal','Metal'],['glass','Glass'],['other','Other']];
const SCREEN = {in:1, out:2, tare:4};
const CODES = {
  in: {ticket:11, cams:[12,13], veh:14, weigh:17, save:18},
  out:{ticket:21, cams:[22,23], veh:24, weigh:27, save:29},
  tare:{ticket:41, cams:[42,43], veh:44, weigh:45, save:46}
};
const SEL = on => ({border: on ? '#0E5230' : 'var(--ink-300)', bg: on ? '#0E5230' : '#fff', fg: on ? '#fff' : 'var(--ink-900)', weight: on ? 700 : 400});
const fmt = n => (n==null||isNaN(n)) ? '—' : Math.round(n).toLocaleString('en-IN');
const kg = n => fmt(n) + ' kg';
const hhmm = () => new Date().toTimeString().slice(0,5);
const hms = () => new Date().toTimeString().slice(0,8);
const norm = s => (s||'').toUpperCase().replace(/[^A-Z0-9 ]/g,'').replace(/\s+/g,' ').trim();
const flat = s => norm(s).replace(/ /g,'');
const pad4 = n => String(n).padStart(4,'0');
const tIn = (src, n, ym) => 'IN' + (src==='Commercial' ? 'C' : 'R') + ym + pad4(n);
const tOut = (n, ym) => 'O' + ym + pad4(n);
const isoDay = d => d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
const shortDay = iso => { const d = new Date(iso + 'T00:00:00'); return d.toLocaleDateString('en-IN', {day:'numeric', month:'short'}); };
const blank = () => ({typed:'', veh:null, source:'Residential', type:'Mixed', material:null, dest:'', manual:false, manualKg:'', reason:null, wbTried:false});
const EMPTY_SRV = {vehicles:[], pending:[], nextIn:1, nextOut:1, yymm:'', dests:[], today:[], queue:[], trips:[], sampleDue:false, month:'', shifts:{count:3, starts:['06:00','14:00','22:00']}};
const EMPTY_LIVE = {wb:{connected:false, weight:0, stable:false}, simulate:false, minKg:10, sync:{state:'offline', queued:0}, cams:{front:{live:false}, back:{live:false}}};

// A small coloured code badge, used everywhere in the prototype.
const badge = (code, bg, fg, extra) => h`<span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:24px;padding:0 7px;border-radius:999px;background:' + bg + ';color:' + fg + ';font-weight:700;font-size:13px;flex:none;' + (extra||''))}>${code}</span>`;

class App extends React.Component {
  constructor(props) {
    super(props);
    const today = isoDay(new Date()), monthAgo = new Date(); monthAgo.setDate(monthAgo.getDate() - 30);
    this.state = {
      boot: null, bootErr: null, loggedIn: false, login: {name:null, pin:'', err:null},
      tab: 'in', in: blank(), out: blank(), tare: blank(), last: {}, busy: false,
      srv: EMPTY_SRV, live: EMPTY_LIVE, dd: null, zoom: {}, full: false, vw: 1366, vh: 620,
      rec: {date: today, arrived:'All', ftype:'All', sel:{}, out:{}, expand:false, msg:null, err:null},
      corr: {open:false, id:null, reason:'', err:null},
      sample: {open:false, kg:'', wet:'', dry:'', inert:'', err:null},
      retrying: false, retryMsg: null,
      rep: {view:'daily', period:'Weekly', from: isoDay(monthAgo), to: today, dir:'Both', data:null, msg:null, file:null},
      admin: {open:false, pin:'', err:null, view:null, draft:null, ops:null, newAdminPin:'', counters:null, msg:null}
    };
  }

  // --- lifecycle -----------------------------------------------------------
  componentDidMount() {
    this.fit = () => { const vw = window.innerWidth || document.documentElement.clientWidth, vh = window.innerHeight || document.documentElement.clientHeight; if (vw && vh) this.setState({vw, vh}); };
    this.fit(); window.addEventListener('resize', this.fit);
    requestAnimationFrame(this.fit); this.fitT = setTimeout(this.fit, 300);
    this.onFs = () => { if (!document.fullscreenElement && !(this.state.boot && this.state.boot.inWindow)) this.setState({full:false}); };
    document.addEventListener('fullscreenchange', this.onFs);
    this.onKey = e => { if (e.key === 'Escape' && this.state.full) this.toggleFull(); };
    window.addEventListener('keydown', this.onKey);
    this.clock = setInterval(() => this.forceUpdate(), 1000);
    this.livePoll = setInterval(() => this.pollLive(), 200);
    this.srvPoll = setInterval(() => { if (this.state.loggedIn) this.refresh(); }, 10000);
    api('boot').then(boot => this.setState({boot, loggedIn: !!boot.operator}, () => this.refresh()))
      .catch(e => this.setState({bootErr: e.message}));
  }
  componentWillUnmount() {
    clearTimeout(this.fitT); window.removeEventListener('resize', this.fit); window.removeEventListener('keydown', this.onKey);
    document.removeEventListener('fullscreenchange', this.onFs); clearInterval(this.clock); clearInterval(this.livePoll); clearInterval(this.srvPoll);
  }
  pollLive() {
    if (this.liveBusy) return;
    this.liveBusy = true;
    api('live').then(live => this.setState({live})).catch(() => {}).finally(() => { this.liveBusy = false; });
  }
  refresh() {
    return api('state').then(srv => this.setState({srv}, () => { if (this.state.tab === 'rep') this.loadReport(); })).catch(() => {});
  }
  loadReport(patch) {
    const RP = {...this.state.rep, ...(patch || {})};
    const args = RP.view === 'custom' ? {view:'custom', period:RP.period, dateFrom:RP.from, dateTo:RP.to, dir:RP.dir} : {view:RP.view};
    const want = JSON.stringify(args);
    this.repWant = want;
    api('report', args).then(data => { if (this.repWant === want) this.setState(st => ({rep:{...st.rep, data, dataFor:want}})); })
      .catch(e => this.setState(st => ({rep:{...st.rep, msg:e.message}})));
  }

  // --- helpers ---------------------------------------------------------------
  setF(flow, patch, cb) { this.setState(s => ({[flow]: {...s[flow], ...patch}}), cb); }
  vehicles() { const m = {}; this.state.srv.vehicles.forEach(v => { m[flat(v.vno)] = v; }); return m; }
  pendingOf(vno) { const k = flat(vno); return this.state.srv.pending.find(p => flat(p.vno) === k); }
  vehStatus(flow, vno) {
    if (!vno) return null;
    const v = this.vehicles()[flat(vno)], known = v && v.tare != null, pend = this.pendingOf(vno);
    if (flow === 'tare') return known ? 'hasTare' : pend ? 'pending' : 'new';
    if (pend) return 'pending';
    return known ? 'known' : 'new';
  }
  tareOf(vno) { const v = this.vehicles()[flat(vno)]; return v && v.tare != null ? v.tare : null; }
  wbOn() { return !!this.state.live.wb.connected; }

  pick(flow, vno) {
    this.setF(flow, {typed:vno, veh:vno});
    api('vehicle_picked', {flow, vno}).catch(() => {});
  }
  goTab(tab) {
    this.setState({tab, dd:null}, () => {
      const f = this.state[tab];
      if (f && f.veh) api('vehicle_picked', {flow:tab, vno:f.veh}).catch(() => {});
      else if (f) api('vehicle_cleared').catch(() => {});
      if (tab === 'rep') this.loadReport();
      this.refresh();
    });
  }
  goTare(vno) { this.setState({tab:'tare', tare:{...blank(), typed:vno, veh:vno}}, () => api('vehicle_picked', {flow:'tare', vno}).catch(() => {})); }
  toggleFull() {
    const on = !this.state.full, inWindow = this.state.boot && this.state.boot.inWindow;
    this.setState({full:on});
    if (inWindow) { api('toggle_full', {on}).catch(() => {}); return; }
    try { if (on && document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {}); else if (!on && document.fullscreenElement) document.exitFullscreen(); } catch (e) {}
  }

  async save(flow) {
    const s = this.state, f = s[flow];
    if (s.busy) return;
    this.setState({busy:true});
    const t = hhmm();
    try {
      let last;
      if (flow === 'in') {
        const r = await api('save_in', {vno:f.veh, source:f.source, type:f.type});
        const e = r.entry;
        last = e.id + ' · ' + t + ' · ' + e.vno + ' · ' + f.source + ', ' + f.type + ' · ' + (e.net_kg != null ? 'net ' + kg(e.net_kg) : 'gross ' + kg(e.gross_kg) + ', tare pending') + ' · ' + r.photos + (r.photos === 1 ? ' photo' : ' photos');
      } else if (flow === 'out') {
        const r = await api('save_out', {vno:f.veh, material:f.material, dest:f.dest, manualKg: f.manual ? f.manualKg : null, reason: f.manual ? f.reason : null});
        const e = r.entry;
        last = e.id + ' · ' + t + ' · ' + f.material + ' to ' + f.dest + ' · net ' + kg(e.net_kg) + (f.manual ? ' · manual' : ' · ' + r.photos + (r.photos === 1 ? ' photo' : ' photos'));
      } else {
        const r = await api('save_tare', {vno:f.veh});
        const p = r.completed[0];
        last = r.tare.vno + ' empty weight ' + kg(r.tare.tare_kg) + (p ? ' · ' + p.id + ' complete, waste in ' + kg(p.net_kg) : '') + ' · ' + t;
      }
      this.setState(st => ({[flow]: blank(), last:{...st.last, [flow]: {ok:true, text:last}}, busy:false}));
      this.refresh();
    } catch (e) {
      this.setState(st => ({last:{...st.last, [flow]: {ok:false, text:e.message}}, busy:false}));
    }
  }

  // --- inward / outward / tare -------------------------------------------------
  work() {
    const flow = this.state.tab, f = this.state[flow], s = this.state, srv = s.srv, cd = CODES[flow];
    const cc = C[SCREEN[flow]], status = this.vehStatus(flow, f.veh), tare = this.tareOf(f.veh);
    const p = f.veh ? this.pendingOf(f.veh) : null;
    const manual = flow==='out' && f.manual;
    const wbDown = !this.wbOn() && !manual;
    const lastRec = s.last[flow];
    const k = {
      cc, ccFg: FG[SCREEN[flow]], isIn: flow==='in', isOut: flow==='out', isTare: flow==='tare', wbDown, wbUp: !wbDown, wbTried: f.wbTried,
      wbSay: 'weighbridge down, ' + (flow==='in'?'green 1':flow==='out'?'blue 2':'yellow 4'),
      screenLabel: SCREEN[flow] + ' ' + ({in:'Inward',out:'Outward',tare:'Tare'})[flow],
      retryWb: () => { this.setF(flow, {wbTried:false}); setTimeout(() => { if (!this.wbOn()) this.setF(flow, {wbTried:true}); }, 1500); },
      useManual: () => this.setF('out', {manual:true}),
      toggleManual: () => { if (f.manual) this.setF('out', {manual:false, manualKg:'', reason:null}); else this.setF('out', {manual:true}); },
      manualToggleLabel: f.manual ? 'Use weighbridge' : 'Small scale',
      hasLast: !!lastRec, lastOk: lastRec && lastRec.ok, lastText: lastRec && lastRec.text,
      weighCode: cd.weigh, saveCode: cd.save, save: () => this.save(flow),
      ticketCode: cd.ticket,
      ticketLabel: flow==='tare' ? 'Tare record' : 'Ticket',
      ticket: flow==='in' ? tIn(f.source, srv.nextIn, srv.yymm) : flow==='out' ? tOut(srv.nextOut, srv.yymm) : (p ? 'for ' + p.id : 'new tare'),
      now: new Date().toLocaleDateString('en-IN',{day:'2-digit', month:'short', year:'numeric'}) + ' · ' + hms()
    };
    const dd = s.dd;
    const open = key => () => { clearTimeout(this.ddT); this.setState({dd:key}); };
    const close = () => { clearTimeout(this.ddT); this.ddT = setTimeout(() => this.setState({dd:null}), 120); };
    // vehicle options: recent vehicles that can be weighed on this screen
    const withTare = srv.vehicles.filter(v => v.tare != null).map(v => v.vno);
    const pendV = srv.pending.map(x => x.vno);
    let base;
    if (flow === 'in') base = srv.vehicles.map(v => v.vno).filter(v => !pendV.includes(v));
    else if (flow === 'out') base = withTare;
    else base = [...pendV, ...srv.vehicles.filter(v => v.tare == null && !pendV.includes(v.vno)).map(v => v.vno)];
    const q = flat(f.typed);
    let list;
    const all = [...new Set([...pendV, ...srv.vehicles.map(v => v.vno)])];
    if (q && !f.veh) {
      list = all.filter(x => flat(x).includes(q)).slice(0,6);
      if (q.length >= 6 && !all.some(x => flat(x) === q)) list = [...list.slice(0,5), norm(f.typed)];
    } else list = [...new Set(base)].slice(0,6);
    const allKnown = new Set(all.map(flat));
    const vehField = {
      code: cd.veh, label: 'Vehicle number', width: flow==='in' ? '290px' : '280px', placeholder: 'Tap to pick or type',
      value: f.typed, readOnly: false, open: dd===flow+'-veh',
      options: list.map(vno => ({label:vno, sub: allKnown.has(flat(vno)) ? (flow==='tare' && pendV.includes(vno) ? 'waiting' : '') : 'new', bg: f.veh===vno ? 'var(--green-050)' : '#fff',
        pick: e => { e.preventDefault(); this.setState({dd:null}); this.pick(flow, vno); }})),
      onFocus: open(flow+'-veh'), onBlur: close,
      onChange: e => { const had = !!f.veh; this.setState({dd:flow+'-veh'}); this.setF(flow, {typed:e.target.value.toUpperCase(), veh:null}); if (had) api('vehicle_cleared').catch(() => {}); },
      onKey: e => { if (e.key === 'Enter' && list.length) { this.setState({dd:null}); this.pick(flow, list[0]); e.target.blur(); } }
    };
    vehField.noOptions = vehField.options.length === 0;
    k.fields = [vehField];
    if (flow === 'out') {
      const mf = {code:25, label:'Material', width:'230px', placeholder:'Tap to pick', value: f.material || '', readOnly:true, open: dd==='out-mat',
        options: MATERIALS.map(m => ({label:m, sub:'', bg: f.material===m ? 'var(--green-050)' : '#fff', pick: e => { e.preventDefault(); this.setState({dd:null}); this.setF('out',{material:m}); }})),
        onFocus: open('out-mat'), onBlur: close, onChange: () => {}, onKey: () => {}};
      const dq = f.dest.trim().toLowerCase();
      const df = {code:26, label:'Going to', width:'280px', placeholder:'Type or pick', value: f.dest, readOnly:false, open: dd==='out-dest',
        options: srv.dests.filter(d => !dq || d.toLowerCase().includes(dq)).map(d => ({label:d, sub:'', bg: f.dest===d ? 'var(--green-050)' : '#fff', pick: e => { e.preventDefault(); this.setState({dd:null}); this.setF('out',{dest:d}); }})),
        onFocus: open('out-dest'), onBlur: close, onChange: e => this.setF('out',{dest:e.target.value}), onKey: e => { if (e.key==='Enter') e.target.blur(); }};
      mf.noOptions = false; df.noOptions = false;
      if (!df.options.length) df.open = false;
      k.fields.push(mf, df);
    }
    // weight status
    const wb = s.live.wb, live = wb.connected ? wb.weight : 0, minKg = s.live.minKg || 10;
    const ok = wb.connected && wb.stable && live > minKg;
    k.showManual = manual; k.showRead = !manual;
    k.readVal = fmt(live);
    const st = (l, bg, fg, t) => { k.stLabel = l; k.stBg = bg; k.stFg = fg; k.stText = t; };
    const AM = [YEL,'#151515'], GR = ['var(--ink-200)','var(--ink-900)'];
    if (manual) st('Manual', ...AM, 'Type the small scale weight and pick a reason.');
    else if (!f.veh) st('Waiting', ...GR, 'Pick the vehicle. Weighing starts by itself.');
    else if (status==='pending' && flow!=='tare') st('Stopped', ...AM, 'Waiting for its empty weight. Weigh it empty on yellow 4 first.');
    else if (flow==='out' && status==='new') st('Stopped', ...AM, 'No empty weight yet. Weigh it empty first.');
    else if (flow==='tare' && status==='hasTare') st('Done', ...GR, 'Already has an empty weight: ' + kg(tare) + '. Nothing to do.');
    else if (!wb.stable) st('Settling', ...AM, 'Keep the vehicle still.');
    else if (live <= minKg) st('Too light', RED, '#fff', 'Weight must be more than ' + fmt(minKg) + ' kg.');
    else st('Stable', GRN, '#fff', flow==='in' && status==='new' ? 'New vehicle: weigh it empty on yellow 4 after unloading.' : 'Ready. Save takes both photos and this weight.');
    k.showGoTare = flow==='out' && (status==='new' || status==='pending');
    k.goTare = () => this.goTare(f.veh);
    k.cams = cd.cams.map((code,i) => {
      const name = i===0 ? 'front' : 'back', key = flow + code, z = (s.zoom||{})[key] || 1;
      const step = d => this.setState(st => { const cur = (st.zoom||{})[key] || 1; return {zoom:{...(st.zoom||{}), [key]: Math.round(Math.min(4, Math.max(1, cur + d))*100)/100}}; });
      const camLive = !!(s.live.cams[name] && s.live.cams[name].live);
      return {code, name, live: camLive, label: i===0 ? 'Front camera' : 'Back camera', z, zLabel: z.toFixed(1) + '×',
        zoomIn: () => step(0.5), zoomOut: () => step(-0.5), zoomReset: () => this.setState(st => ({zoom:{...(st.zoom||{}), [key]: 1}})),
        onWheel: e => step(e.deltaY < 0 ? 0.25 : -0.25)};
    });
    k.manualKg = f.manualKg || '';
    k.onManualKg = e => this.setF('out', {manualKg:e.target.value});
    k.reasons = ['Small scale (1 ton)','Weighbridge not working','Load too small'].map(r => ({label:r, ...SEL(f.reason===r), pick: () => this.setF('out',{reason:r})}));
    const cell = (kk, vv, hi) => ({k:kk, v:vv, bg: hi ? '#0E5230' : 'var(--ink-100)', fg: hi ? '#BFEBC9' : 'var(--ink-700)', vc: hi ? '#fff' : 'var(--ink-900)', size: '22px'});
    k.readLabel = flow==='tare' ? 'Tare · empty weight' : 'Gross · live';
    if (flow === 'in') {
      k.trio = [cell('Tare', tare != null ? kg(tare) : f.veh ? 'After unload' : '—'),
        cell('Net', live > 0 && tare != null ? kg(Math.max(0, live - tare)) : f.veh && tare == null && status!=='pending' ? 'Pending' : '—', true)];
    } else if (flow === 'out') {
      k.trio = [cell('Tare', tare != null ? kg(tare) : '—'), cell('Net', live > 0 && tare != null ? kg(Math.max(0, live - tare)) : '—', true)];
    } else {
      k.trio = [cell('Gross (came in)', p ? kg(p.gross) : '—'),
        cell('Net', p && live > 0 ? kg(Math.max(0, p.gross - live)) : '—', true)];
    }
    k.sources = ['Residential','Commercial'].map(o => ({label:o, ...SEL(f.source===o), pick: () => this.setF('in',{source:o})}));
    k.types = IN_TYPES.map(o => ({label:o, ...SEL(f.type===o), pick: () => this.setF('in',{type:o})}));
    k.saveLabel = 'Save';
    if (flow === 'in') k.saveDisabled = !(f.veh && ok && status !== 'pending');
    else if (flow === 'out') k.saveDisabled = !(status==='known' && f.material && f.dest.trim() && (manual ? Number(f.manualKg) > 0 && f.reason : ok));
    else k.saveDisabled = !(f.veh && ok && status !== 'hasTare');
    if (s.busy) k.saveDisabled = true;
    return k;
  }

  // --- render ------------------------------------------------------------------
  render() {
    const s = this.state;
    if (s.bootErr) return h`<div style=${css('padding:40px;font-size:22px;color:#C62828')}>${s.bootErr}</div>`;
    if (!s.boot) return null;
    const vw = s.vw, vh = s.vh;
    let fit = Math.min(vw/1366, vh/620); if (!isFinite(fit) || fit <= 0) fit = 1;
    const scale = s.full ? fit : Math.min(fit, 1);
    return h`
<div style=${css('position:fixed;inset:0;background:var(--green-050);display:flex;align-items:center;justify-content:center;overflow:hidden')}>
<div data-screen-label="ISWM Plant App" style=${css('width:1366px;height:620px;flex:none;transform:scale(' + scale + ');transform-origin:center;background:#fff;box-shadow:var(--shadow-lg);display:flex;flex-direction:column;position:relative;overflow:hidden;color:var(--ink-700)')}>
${s.loggedIn ? this.renderApp() : this.renderLogin()}
${this.renderDialogs()}
</div>
</div>`;
  }

  renderLogin() {
    const s = this.state, L = s.login, boot = s.boot;
    const tryPin = (name, pin) => {
      if (!name || pin.length !== 4) return;
      api('login', {name, pin}).then(() => this.setState(st => ({boot:{...st.boot, operator:name}, loggedIn:true, login:{name:null, pin:'', err:null}, tab:'in'}), () => this.refresh()))
        .catch(e => this.setState({login:{name, pin:'', err:e.message}}));
    };
    const loginNames = boot.operators.map(name => ({name, ...SEL(L.name===name), pick: () => { this.setState({login:{...L, name, err:null}}); tryPin(name, L.pin); }}));
    const press = key => () => {
      const pin = L.pin, np = key==='C' ? '' : key==='<' ? pin.slice(0,-1) : (pin + key).slice(0,4);
      this.setState({login:{...L, pin:np, err:null}});
      tryPin(L.name, np);
    };
    const keypad = ['1','2','3','4','5','6','7','8','9','C','0','<'].map(x => ({label: x==='C' ? 'Clear' : x==='<' ? '←' : x, press: press(x)}));
    const pinDots = [0,1,2,3].map(i => ({bg: i < L.pin.length ? 'var(--green-700)' : '#fff'}));
    return h`
<div data-screen-label="0 Start shift" style=${css('flex:1;display:flex;align-items:center;justify-content:center;gap:96px;padding:48px;position:relative')}>
  <div style=${css('display:flex;flex-direction:column;gap:18px;max-width:420px')}>
    <div style=${css('font-size:12px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:var(--green-700)')}>${boot.agency}</div>
    <div style=${css('font-size:52px;line-height:1.08;letter-spacing:-0.015em;color:var(--ink-900)')}>${boot.site}.</div>
    <div style=${css('font-size:22px;line-height:1.4;color:var(--ink-700)')}>Tap your name, then type your 4-number PIN. The shift starts by itself.</div>
  </div>
  <div style=${css('display:flex;flex-direction:column;gap:22px;width:420px')}>
    <div style=${css('display:grid;grid-template-columns:repeat(3,1fr);gap:10px')}>
      ${loginNames.map(n => h`<button key=${n.name} onClick=${n.pick} style=${css('height:72px;border-radius:16px;border:2px solid ' + n.border + ';background:' + n.bg + ';font-size:19px;font-weight:700;color:' + n.fg + ';cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 8px')}>${n.name}</button>`)}
    </div>
    <div style=${css('display:flex;justify-content:center;gap:18px;padding:6px 0')}>
      ${pinDots.map((d, i) => h`<span key=${i} style=${css('width:22px;height:22px;border-radius:50%;border:2px solid var(--green-700);background:' + d.bg)}></span>`)}
    </div>
    <div style=${css('display:grid;grid-template-columns:repeat(3,1fr);gap:10px')}>
      ${keypad.map(k => h`<button key=${k.label} onClick=${k.press} style=${css('height:64px;border-radius:16px;border:2px solid var(--ink-300);background:#fff;font-size:28px;color:var(--ink-900);cursor:pointer')}>${k.label}</button>`)}
    </div>
    <div style=${css('font-size:14px;color:' + (L.err ? '#C62828' : 'var(--ink-700)') + ';text-align:center;font-weight:' + (L.err ? 700 : 400))}>
      ${L.err ? L.err : !L.name ? 'Tap your name first.' : boot.defaultPins ? 'First time? The PIN is 0000. Ask the admin to change it.' : ' '}
    </div>
  </div>
  ${this.gearButton('position:absolute;right:16px;bottom:16px')}
</div>`;
  }

  gearButton(extra) {
    return h`<button onClick=${() => this.setState(st => ({admin:{...st.admin, open:true, pin:'', err:null, view:null}}))} title="Admin settings" aria-label="Admin settings" style=${css('display:flex;align-items:center;justify-content:center;flex:none;width:38px;height:38px;padding:0;border-radius:50%;border:2px solid var(--ink-300);background:#fff;color:var(--ink-900);cursor:pointer;' + (extra||''))}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle></svg></button>`;
  }

  renderApp() {
    const s = this.state, srv = s.srv, boot = s.boot;
    const mode = s.live.sync.state, qn = s.live.sync.queued;
    const syncPill = mode==='synced' ? {label:'Synced', bg:GRN, fg:'#fff'}
      : mode==='error' ? {label:'Sync error', bg:RED, fg:'#fff'}
      : mode==='off' ? {label:'Sync off', bg:'#E8EDEA', fg:'#151515'}
      : {label:'Offline · ' + qn + ' queued', bg:'#E8EDEA', fg:'#151515'};
    const wbOff = !this.wbOn();
    const tabs = [['in',1,'Inward'],['out',2,'Outward'],['rec',3,'Material recovery'],['tare',4,'Tare'],['sync',5,'Sync'],['rep',6,'Reports']].map(([id,n,label]) => {
      const on = s.tab===id;
      return {id, n, label, color: on ? '#fff' : C[n], fg: on ? (n===4 ? '#151515' : C[n]) : FG[n], tfg: on ? FG[n] : 'var(--ink-900)', border: on ? (n===4 ? '#151515' : C[n]) : 'var(--ink-300)', bg: on ? C[n] : '#fff', weight: on ? 700 : 400,
        hasCount: id==='tare' && srv.pending.length>0, count: srv.pending.length, go: () => this.goTab(id)};
    });
    const isWork = ['in','out','tare'].includes(s.tab);
    const screenColor = C[{in:1,out:2,rec:3,tare:4,sync:5,rep:6}[s.tab]];
    const fullLabel = s.full ? 'Exit full view' : 'Full view';
    const fullIcon = s.full ? 'M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3' : 'M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3';
    const endShift = () => { if (window.confirm('End shift for ' + boot.operator + '?')) api('logout').then(() => this.setState(st => ({loggedIn:false, boot:{...st.boot, operator:null}}))); };
    return h`
<div style=${css('height:64px;flex:none;display:flex;align-items:center;gap:12px;padding:0 16px;background:#fff')}>
  <div style=${css('display:flex;flex-direction:column;line-height:1.15;flex:none;white-space:nowrap')}>
    <span style=${css('font-size:17px;font-weight:700;color:var(--ink-900)')}>${boot.site}</span>
    <span style=${css('font-size:12px;color:var(--ink-700)')}>${boot.agency}</span>
  </div>
  <div style=${css('display:flex;gap:2px;flex:1;min-width:0;justify-content:center')}>
    ${tabs.map(t => h`<button key=${t.id} onClick=${t.go} style=${css('display:flex;align-items:center;gap:7px;height:44px;padding:0 11px 0 6px;white-space:nowrap;flex:none;border-radius:999px;border:2px solid ' + t.border + ';background:' + t.bg + ';cursor:pointer;font-size:16px;font-weight:' + t.weight + ';color:' + t.tfg)}>
        <span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:30px;padding:0 6px;border-radius:999px;background:' + t.color + ';color:' + t.fg + ';font-weight:700;font-size:15px')}>${t.n}</span>
        ${t.label}
        ${t.hasCount && h`<span style=${css('min-width:22px;height:22px;padding:0 6px;border-radius:999px;background:#F2C200;color:#151515;border:1px solid #151515;font-size:13px;font-weight:700;display:inline-flex;align-items:center;justify-content:center')}>${t.count}</span>`}
      </button>`)}
  </div>
  <div style=${css('display:flex;align-items:center;gap:8px;flex:none')}>
    ${wbOff && h`<div style=${css('display:flex;align-items:center;gap:7px;height:36px;padding:0 12px;white-space:nowrap;border-radius:999px;background:' + RED + ';color:#fff;font-size:14px;font-weight:700')}><span style=${css('width:9px;height:9px;border-radius:50%;background:#fff')}></span>Bridge off</div>`}
    <button onClick=${() => this.goTab('sync')} style=${css('display:flex;align-items:center;gap:8px;height:36px;padding:0 12px 0 4px;white-space:nowrap;border-radius:999px;border:2px solid #151515;background:' + syncPill.bg + ';color:' + syncPill.fg + ';font-size:14px;font-weight:700;cursor:pointer')}>
      <span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:28px;border-radius:999px;background:#151515;color:#fff;font-size:14px;box-shadow:0 0 0 2px #fff')}>5</span>${syncPill.label}
    </button>
    <button onClick=${() => this.toggleFull()} title=${fullLabel} aria-label=${fullLabel} style=${css('display:flex;align-items:center;justify-content:center;flex:none;width:38px;height:38px;padding:0;border-radius:50%;border:2px solid var(--ink-300);background:#fff;color:var(--ink-900);cursor:pointer')}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d=${fullIcon}></path></svg></button>
    ${this.gearButton()}
    <button onClick=${endShift} title="End shift" style=${css('display:flex;flex-direction:column;align-items:flex-end;line-height:1.2;padding:0 0 0 4px;white-space:nowrap;border:none;background:none;cursor:pointer')}>
      <span style=${css('font-size:14px;font-weight:700;color:var(--ink-900)')}>${boot.operator}</span>
      <span style=${css('font-size:12px;color:var(--ink-700)')}>End shift</span>
    </button>
  </div>
</div>
<div style=${css('height:6px;flex:none;background:' + screenColor)}></div>
<div style=${css('flex:1;min-height:0;display:flex')}>
${isWork && this.renderWork()}
${s.tab==='rec' && this.renderRec()}
${s.tab==='rep' && this.renderRep()}
${s.tab==='sync' && this.renderSync()}
</div>`;
  }

  renderWork() {
    const k = this.work(), s = this.state, srv = s.srv;
    const fieldInput = {fontSize:'21px', padding:'13px 16px', letterSpacing:'0.02em', width:'100%', boxSizing:'border-box', cursor:'text'};
    const hugeInput = {fontSize:'34px', padding:'6px 14px', width:'100%', boxSizing:'border-box'};
    const big = {style:{padding:'16px 30px', fontSize:'22px', whiteSpace:'nowrap'}};
    const huge = {style:{width:'100%', justifyContent:'center', padding:'22px 20px', fontSize:'24px', whiteSpace:'nowrap'}};
    const seg = (o) => h`<button key=${o.label} onClick=${o.pick} style=${css('height:52px;padding:0 15px;border-radius:999px;border:2px solid ' + o.border + ';background:' + o.bg + ';font-size:17px;font-weight:' + o.weight + ';color:' + o.fg + ';cursor:pointer;white-space:nowrap')}>${o.label}</button>`;
    return h`
<${React.Fragment}>
<div data-screen-label=${k.screenLabel} style=${css('flex:1;min-width:0;display:flex;flex-direction:column;gap:14px;padding:16px 24px 18px')}>
  ${k.wbDown && h`
  <div style=${css('flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;text-align:center;background:#FDECEC;border:3px solid #C62828;border-radius:24px;padding:40px')}>
    <div style=${css('font-size:13px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:#C62828')}>Weighing stopped</div>
    <div style=${css('font-size:48px;line-height:1.08;letter-spacing:-0.015em;color:var(--ink-900)')}>Weighbridge not connected.</div>
    <div style=${css('font-size:22px;line-height:1.45;max-width:640px;color:var(--ink-700)')}>Check the cable at the weighbridge display. Then call support and say “${k.wbSay}”.</div>
    <${Button} size="lg" onClick=${k.retryWb} ...${big}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:28px;padding:0 7px;border-radius:999px;background:' + k.cc + ';box-shadow:0 0 0 2px #fff;color:' + k.ccFg + ';font-size:15px')}>${k.weighCode}</span>Try again<//>
    ${k.wbTried && h`<div style=${css('font-size:17px;color:#C62828;font-weight:700')}>Still not connected.</div>`}
    ${k.isOut && h`<button onClick=${k.useManual} style=${css('display:flex;align-items:center;gap:8px;border:none;background:none;font-size:18px;color:var(--green-700);font-weight:700;cursor:pointer')}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:26px;border-radius:999px;background:#1D5FC2;color:#fff;font-size:14px')}>28</span>Use small scale instead</button>`}
  </div>`}

  ${k.wbUp && h`
  <${React.Fragment}>
    <div style=${css('flex:none;display:flex;align-items:center;gap:14px;height:40px')}>
      <div style=${css('display:flex;align-items:center;gap:10px;height:40px;padding:0 14px 0 6px;border-radius:999px;background:var(--ink-050);border:1px solid var(--ink-100);flex:none;white-space:nowrap')}>
        <span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:26px;padding:0 7px;border-radius:999px;background:' + k.cc + ';color:' + k.ccFg + ';font-weight:700;font-size:14px')}>${k.ticketCode}</span>
        <span style=${css('font-size:13px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:var(--ink-700)')}>${k.ticketLabel}</span>
        <span style=${css('font-size:20px;font-weight:700;color:var(--ink-900);letter-spacing:0.03em;font-variant-numeric:tabular-nums')}>${k.ticket}</span>
        <span style=${css('width:1px;height:20px;background:var(--ink-200)')}></span>
        <span style=${css('font-size:17px;color:var(--ink-900);font-variant-numeric:tabular-nums')}>${k.now}</span>
      </div>
      ${k.hasLast && h`
        <div style=${css('flex:1;min-width:0;display:flex;align-items:center;gap:10px;height:40px;padding:0 14px 0 6px;border-radius:999px;background:' + (k.lastOk ? 'var(--green-050)' : '#FDECEC') + ';border:1px solid ' + (k.lastOk ? 'var(--green-200)' : '#C62828'))}>
          <span style=${css('padding:3px 10px;border-radius:999px;background:' + (k.lastOk ? 'var(--green-600)' : '#C62828') + ';color:#fff;font-size:13px;font-weight:700;flex:none')}>${k.lastOk ? 'Saved' : 'Not saved'}</span>
          <span style=${css('flex:1;min-width:0;font-size:15px;color:var(--ink-900);white-space:nowrap;overflow:hidden;text-overflow:ellipsis')}>${k.lastText}</span>
          ${k.lastOk && h`<span style=${css('font-size:13px;color:var(--ink-700);white-space:nowrap;flex:none')}>Wrong? Black 5 → 52</span>`}
        </div>`}
    </div>

    <div style=${css('flex:1;min-height:170px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px')}>
      ${k.cams.map(cam => h`
        <div key=${cam.code} onWheel=${cam.onWheel} style=${css('border-radius:16px;background:#C9CFCB;border:2px solid #9AA79F;position:relative;overflow:hidden;min-width:0')}>
          ${cam.live ? h`<img key=${'img' + cam.name} class="cam-img" src=${camUrl(cam.name)} alt=${cam.label} style=${{transform:'scale(' + cam.z + ')'}} />`
            : h`<div style=${css('position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:10px;color:var(--ink-700);font-size:18px;font-weight:700;white-space:nowrap;transform:scale(' + cam.z + ');transition:transform 150ms cubic-bezier(0.22,1,0.36,1)')}>
              <span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:28px;padding:0 7px;border-radius:999px;background:' + k.cc + ';color:' + k.ccFg + ';font-size:15px')}>${cam.code}</span>${cam.label}
            </div>`}
          <span style=${css('position:absolute;left:12px;top:12px;display:flex;align-items:center;gap:6px;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:' + (cam.live ? '#fff' : 'var(--ink-700)') + ';' + (cam.live ? 'padding:3px 8px;border-radius:999px;background:rgba(18,26,20,0.55)' : ''))}><span style=${css('width:8px;height:8px;border-radius:50%;background:' + (cam.live ? 'var(--red-600)' : 'var(--ink-500)'))}></span>${cam.live ? h`<span style=${css('display:inline-flex;align-items:center;gap:6px')}>${cam.code} · Live</span>` : 'No signal'}</span>
          <div style=${css('position:absolute;right:10px;bottom:10px;display:flex;align-items:center;gap:4px;padding:4px;border-radius:999px;background:#fff;box-shadow:var(--shadow-md)')}>
            <button onClick=${cam.zoomOut} aria-label="Zoom out" style=${css('width:40px;height:40px;border-radius:50%;border:none;background:var(--ink-050);font-size:24px;line-height:1;color:var(--ink-900);cursor:pointer')}>−</button>
            <button onClick=${cam.zoomReset} style=${css('min-width:52px;height:40px;border:none;background:none;font-size:15px;font-weight:700;color:var(--ink-900);cursor:pointer')}>${cam.zLabel}</button>
            <button onClick=${cam.zoomIn} aria-label="Zoom in" style=${css('width:40px;height:40px;border-radius:50%;border:none;background:var(--ink-050);font-size:24px;line-height:1;color:var(--ink-900);cursor:pointer')}>+</button>
          </div>
        </div>`)}
    </div>

    <div style=${css('flex:none;display:flex;align-items:stretch;gap:12px')}>
      ${k.fields.map(fd => h`
        <div key=${fd.code} style=${css('position:relative;display:flex;flex-direction:column;gap:6px;width:' + fd.width + ';flex:none;padding:8px 10px;border:2px solid var(--ink-300);border-radius:14px;background:#fff')}>
          <span style=${css('display:flex;align-items:center;gap:8px;font-size:15px;font-weight:700;color:var(--ink-900);white-space:nowrap')}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:24px;padding:0 7px;border-radius:999px;background:' + k.cc + ';color:' + k.ccFg + ';font-size:13px')}>${fd.code}</span>${fd.label}</span>
          <${Input} placeholder=${fd.placeholder} value=${fd.value} readOnly=${fd.readOnly} onChange=${fd.onChange} onFocus=${fd.onFocus} onBlur=${fd.onBlur} onKeyDown=${fd.onKey} inputStyle=${fieldInput} />
          ${fd.open && h`
            <div style=${css('position:absolute;left:0;right:0;bottom:calc(100% + 6px);z-index:30;background:#fff;border:2px solid var(--ink-300);border-radius:14px;box-shadow:var(--shadow-lg);padding:6px;display:flex;flex-direction:column;max-height:300px;overflow:auto')}>
              ${fd.options.map(o => h`
                <button key=${o.label} onMouseDown=${o.pick} style=${css('display:flex;align-items:baseline;justify-content:space-between;gap:10px;height:48px;flex:none;padding:0 14px;border:none;border-radius:10px;background:' + o.bg + ';cursor:pointer;text-align:left;white-space:nowrap')}>
                  <span style=${css('font-size:20px;color:var(--ink-900);letter-spacing:0.02em')}>${o.label}</span>
                  <span style=${css('font-size:13px;color:var(--green-700);font-weight:700')}>${o.sub}</span>
                </button>`)}
              ${fd.noOptions && h`<div style=${css('padding:12px 14px;font-size:15px;color:var(--ink-700)')}>Type the full number.</div>`}
            </div>`}
        </div>`)}
      ${k.isIn && h`
        <${React.Fragment}>
        <div style=${css('display:flex;flex-direction:column;gap:6px;flex:none;padding:8px 10px;border:2px solid var(--ink-300);border-radius:14px;background:#fff')}>
          <span style=${css('display:flex;align-items:center;gap:8px;font-size:15px;font-weight:700;color:var(--ink-900)')}>${badge(15, '#1B8A3A', '#fff')}From</span>
          <div style=${css('display:flex;gap:6px')}>${k.sources.map(seg)}</div>
        </div>
        <div style=${css('display:flex;flex-direction:column;gap:6px;flex:none;padding:8px 10px;border:2px solid var(--ink-300);border-radius:14px;background:#fff')}>
          <span style=${css('display:flex;align-items:center;gap:8px;font-size:15px;font-weight:700;color:var(--ink-900)')}>${badge(16, '#1B8A3A', '#fff')}Waste</span>
          <div style=${css('display:flex;gap:6px')}>${k.types.map(seg)}</div>
        </div>
        <//>`}
    </div>

    <div style=${css('flex:none;display:flex;align-items:center;gap:14px;padding:12px 12px 12px 16px;border-radius:20px;border:2px solid var(--ink-300);background:#fff')}>
      <div style=${css('width:140px;flex:none;display:flex;flex-direction:column;gap:6px')}>
        <div style=${css('display:flex;align-items:center;gap:8px')}>
          <span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:26px;padding:0 7px;border-radius:999px;background:' + k.cc + ';color:' + k.ccFg + ';font-weight:700;font-size:14px')}>${k.weighCode}</span>
          <span style=${css('padding:3px 12px;border-radius:999px;background:' + k.stBg + ';color:' + k.stFg + ';font-size:14px;font-weight:700;white-space:nowrap')}>${k.stLabel}</span>
        </div>
        <span style=${css('font-size:14px;line-height:1.3;color:var(--ink-700)')}>${k.stText}</span>
        ${k.showGoTare && h`<button onClick=${k.goTare} style=${css('align-self:flex-start;display:flex;align-items:center;gap:6px;height:34px;padding:0 12px 0 4px;border-radius:999px;border:none;background:var(--green-600);color:#fff;font-size:14px;font-weight:700;cursor:pointer;white-space:nowrap')}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:24px;padding:0 7px;border-radius:999px;background:#F2C200;color:#151515;font-weight:700;font-size:12px;flex:none')}>4</span>Go to Tare</button>`}
        ${k.isOut && h`<button onClick=${k.toggleManual} style=${css('align-self:flex-start;display:flex;align-items:center;gap:6px;border:none;background:none;padding:0;font-size:14px;color:var(--green-700);font-weight:700;cursor:pointer;white-space:nowrap')}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:22px;padding:0 7px;border-radius:999px;background:#1D5FC2;color:#fff;font-weight:700;font-size:12px;flex:none')}>28</span>${k.manualToggleLabel}</button>`}
      </div>
      ${k.showRead && h`
        <${React.Fragment}>
        <div style=${css('display:flex;flex-direction:column;gap:2px;flex:none;width:240px')}>
          <span style=${css('font-size:12px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:var(--ink-700)')}>${k.readLabel}</span>
          <span style=${css('display:flex;align-items:baseline;gap:8px;white-space:nowrap')}><span style=${css('font-size:64px;line-height:1;letter-spacing:-0.02em;color:var(--ink-900);font-variant-numeric:tabular-nums')}>${k.readVal}</span><span style=${css('font-size:22px;color:var(--ink-700)')}>kg</span></span>
        </div>
        <div style=${css('flex:1;min-width:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px')}>
          ${k.trio.map(x => h`
            <div key=${x.k} style=${css('display:flex;flex-direction:column;gap:2px;padding:9px 10px;border-radius:12px;background:' + x.bg + ';min-width:0')}>
              <span style=${css('font-size:12px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:' + x.fg + ';white-space:nowrap')}>${x.k}</span>
              <span style=${css('font-size:' + x.size + ';line-height:1.1;color:' + x.vc + ';font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums')}>${x.v}</span>
            </div>`)}
        </div>
        <//>`}
      ${k.showManual && h`
        <div style=${css('flex:1;min-width:0;display:flex;align-items:flex-end;gap:14px')}>
          <${Input} label="Small scale (kg)" placeholder="0" type="number" value=${k.manualKg} onChange=${k.onManualKg} inputStyle=${hugeInput} style=${{width:'210px', flex:'none'}} />
          <div style=${css('display:flex;flex-direction:column;gap:6px;min-width:0')}>
            <span style=${css('font-size:14px;font-weight:700;color:var(--ink-900)')}>Why? Marked manual.</span>
            <div style=${css('display:flex;gap:6px;flex-wrap:wrap')}>
              ${k.reasons.map(r => h`<button key=${r.label} onClick=${r.pick} style=${css('height:40px;padding:0 12px;border-radius:999px;border:2px solid ' + r.border + ';background:' + r.bg + ';font-size:14px;color:' + r.fg + ';cursor:pointer;white-space:nowrap')}>${r.label}</button>`)}
            </div>
          </div>
        </div>`}
      <div style=${css('flex:none;width:150px')}>
        <${Button} size="lg" disabled=${k.saveDisabled} onClick=${k.save} ...${huge}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:34px;height:32px;padding:0 8px;border-radius:999px;background:' + k.cc + ';box-shadow:0 0 0 2px #fff;color:' + k.ccFg + ';font-size:17px')}>${k.saveCode}</span>${k.saveLabel}<//>
      </div>
    </div>
  <//>`}
</div>

${s.tab==='in' && h`
<div style=${css('width:260px;flex:none;border-left:1px solid var(--ink-100);background:var(--green-050);display:flex;flex-direction:column;padding:18px 16px;gap:10px;overflow-y:auto')}>
  <div style=${css('display:flex;align-items:center;gap:10px')}>
    <span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:26px;border-radius:999px;background:#1B8A3A;color:#fff;font-weight:700;font-size:14px;flex:none')}>19</span>
    <span style=${css('font-size:19px;color:var(--ink-900)')}>Waiting for empty weight</span>
  </div>
  <div style=${css('font-size:15px;color:var(--ink-700)')}>Unloaded? Tap one. It opens on the bridge, ready to weigh.</div>
  ${srv.pending.map(x => h`
    <button key=${x.id} onClick=${() => this.goTare(x.vno)} style=${css('display:flex;flex-direction:column;gap:5px;text-align:left;padding:12px 14px;border-radius:16px;border:2px solid var(--ink-300);background:#fff;cursor:pointer;box-shadow:var(--shadow-sm);flex:none')}>
      <span style=${css('font-size:20px;font-weight:700;color:var(--ink-900)')}>${x.vno}</span>
      <span style=${css('font-size:14px;color:var(--ink-700)')}>${x.id + ' · in at ' + x.time + ' · full ' + kg(x.gross)}</span>
      <span style=${css('font-size:15px;font-weight:700;color:var(--green-700)')}>Weigh empty now</span>
    </button>`)}
  ${srv.pending.length===0 && h`<div style=${css('font-size:16px;color:var(--ink-700);padding:16px;border-radius:16px;border:1px dashed var(--ink-200);text-align:center')}>No vehicles waiting.</div>`}
</div>`}
<//>`;
  }

  // --- 3 material recovery --------------------------------------------------
  renderRec() {
    const s = this.state, srv = s.srv, R = s.rec;
    const days = [...new Set(srv.trips.map(t => t.day))].slice(-3);
    const arrivedOpts = ['All', ...days];
    const visible = srv.trips.filter(t => (R.arrived==='All' || t.day===R.arrived) && (R.ftype==='All' || t.type===R.ftype));
    const chosen = srv.trips.filter(t => R.sel[t.id]);
    const sum = x => chosen.filter(t => !x || t.type===x).reduce((a,t) => a+t.net, 0);
    const input = sum();
    const ov = x => Number(R.out[x]) || 0;
    const recyc = RECYC.reduce((a,[x]) => a + ov(x), 0);
    const recovered = ov('compost') + ov('rdf') + recyc, allOut = recovered + ov('disposal');
    const setRec = patch => this.setState(st => ({rec:{...st.rec, ...patch}}));
    const setOut = x => e => { const val = e.target.value; this.setState(st => ({rec:{...st.rec, out:{...st.rec.out, [x]:val}, msg:null, err:null}})); };
    const inRow = (x,label,indent,size) => ({key:x, label, isInput:true, isGroup:false, val:R.out[x]||'', onChange:setOut(x), indent:indent||'0px', size:size||'18px'});
    const outRows = [inRow('compost','Compost'), inRow('rdf','RDF'),
      {key:'recyc', label:'Recyclables', isInput:false, isGroup:true, sum:kg(recyc), indent:'0px', size:'20px'},
      ...(R.expand ? RECYC.map(([x,l]) => inRow(x,l,'18px','17px')) : []), inRow('disposal','Disposal (landfill)')];
    const seg = (opts, cur, key, label) => opts.map(o => { const sl = SEL(cur===o); return h`<button key=${o} onClick=${() => setRec({[key]:o})} style=${css('height:36px;padding:0 12px;border-radius:999px;border:2px solid ' + sl.border + ';background:' + sl.bg + ';font-size:15px;color:' + sl.fg + ';cursor:pointer;white-space:nowrap')}>${label ? label(o) : o}</button>`; });
    const allOn = visible.length>0 && visible.every(t => R.sel[t.id]);
    const inTotals = [{k:'Mixed',v:kg(sum('Mixed')),size:'20px'},{k:'Wet',v:kg(sum('Wet')),size:'20px'},{k:'Dry',v:kg(sum('Dry')),size:'20px'},{k:'Total in · ' + chosen.length + ' trips',v:kg(input),size:'22px'}];
    const kgInput = {width:'100%', boxSizing:'border-box', textAlign:'right', fontSize:'18px', padding:'6px 12px'};
    const brown = '#7B4A1F';
    const saveBatch = () => api('save_batch', {date:R.date, ids:chosen.map(t => t.id), outputs:R.out})
      .then(r => { this.setState(st => ({rec:{...st.rec, sel:{}, out:{}, expand:false, err:null, msg:'Batch ' + r.id + ' saved. ' + r.trips + ' trips processed.'}})); this.refresh(); })
      .catch(e => setRec({err:e.message, msg:null}));
    return h`
<div data-screen-label="3 Material recovery" style=${css('flex:1;min-width:0;display:flex;flex-direction:column;gap:10px;padding:12px 24px 14px')}>
  ${srv.sampleDue && h`
    <div style=${css('display:flex;align-items:center;justify-content:space-between;gap:16px;padding:6px 8px 6px 18px;border-radius:14px;background:#FFF3B8;border:2px solid #F2C200')}>
      <span style=${css('font-size:16px;color:var(--ink-900)')}><b>Mixed sample due for ${srv.month}.</b> Weigh one sample of mixed waste and split it.</span>
      <${Button} onClick=${() => this.setState(st => ({sample:{...st.sample, open:true, err:null}}))} style=${{whiteSpace:'nowrap'}}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:26px;padding:0 6px;border-radius:999px;background:#7B4A1F;box-shadow:0 0 0 2px #fff;color:#fff;font-size:14px')}>37</span>Record sample<//>
    </div>`}
  <div style=${css('flex:1;min-height:0;display:flex;gap:14px')}>
    <div style=${css('flex:1.45;min-width:0;display:flex;flex-direction:column;border:2px solid var(--ink-300);border-radius:20px;overflow:hidden')}>
      <div style=${css('padding:10px 16px 10px;display:flex;flex-direction:column;gap:8px;border-bottom:1px solid var(--ink-200)')}>
        <span style=${css('font-size:20px;color:var(--ink-900)')}>1. Tick the trips you processed.</span>
        <div style=${css('display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap')}>
          <div style=${css('display:flex;flex-direction:column;gap:6px')}>
            <span style=${css('display:flex;align-items:center;gap:6px;font-size:14px;font-weight:700;color:var(--ink-900)')}>${badge(31, brown, '#fff', 'min-width:26px;height:22px;font-size:12px;padding:0')}Processing date</span>
            <input type="date" value=${R.date} onChange=${e => setRec({date:e.target.value})} style=${css('height:36px;padding:0 10px;border-radius:10px;border:2px solid var(--ink-300);font-family:var(--font-body);font-size:16px;color:var(--ink-900)')} />
          </div>
          <div style=${css('display:flex;flex-direction:column;gap:6px')}>
            <span style=${css('display:flex;align-items:center;gap:6px;font-size:14px;font-weight:700;color:var(--ink-900)')}>${badge(32, brown, '#fff', 'min-width:26px;height:22px;font-size:12px;padding:0')}Arrived</span>
            <div style=${css('display:flex;gap:6px')}>${seg(arrivedOpts, R.arrived, 'arrived', o => o==='All' ? 'All' : shortDay(o))}</div>
          </div>
          <div style=${css('display:flex;flex-direction:column;gap:6px')}>
            <span style=${css('display:flex;align-items:center;gap:6px;font-size:14px;font-weight:700;color:var(--ink-900)')}>${badge(33, brown, '#fff', 'min-width:26px;height:22px;font-size:12px;padding:0')}Waste type</span>
            <div style=${css('display:flex;gap:6px')}>${seg(['All', ...IN_TYPES], R.ftype, 'ftype')}</div>
          </div>
        </div>
      </div>
      <div style=${css('display:flex;align-items:center;gap:10px;padding:6px 16px;background:var(--ink-050);border-bottom:1px solid var(--ink-200)')}>
        ${badge(34, brown, '#fff', 'min-width:26px;height:22px;font-size:12px;padding:0')}
        <${Checkbox} label="Select all" checked=${allOn} onChange=${() => { const sel = {...R.sel}; visible.forEach(t => { sel[t.id] = !allOn; }); setRec({sel}); }} />
        <span style=${css('margin-left:auto;font-size:14px;color:var(--ink-700)')}>${visible.length + ' trips not processed'}</span>
      </div>
      <div style=${css('flex:1;min-height:0;overflow-y:auto;overflow-x:hidden')}>
        ${visible.map(t => h`
          <div key=${t.id} style=${css('display:grid;grid-template-columns:140px minmax(0,1fr) 112px 50px 80px;align-items:center;gap:6px;padding:6px 14px;border-bottom:1px solid var(--ink-200);background:' + (R.sel[t.id] ? '#E4F6E9' : '#fff'))}>
            <${Checkbox} label=${t.id} checked=${!!R.sel[t.id]} onChange=${() => setRec({sel:{...R.sel, [t.id]: !R.sel[t.id]}})} />
            <span style=${css('font-size:16px;color:var(--ink-900);white-space:nowrap;overflow:hidden;text-overflow:ellipsis')}>${t.vno}</span>
            <span style=${css('font-size:15px;color:var(--ink-700);white-space:nowrap')}>${shortDay(t.day) + ' · ' + t.time}</span>
            <span style=${css('font-size:15px;color:var(--ink-700)')}>${t.type}</span>
            <span style=${css('font-size:17px;color:var(--ink-900);text-align:right;font-variant-numeric:tabular-nums')}>${kg(t.net)}</span>
          </div>`)}
        ${visible.length===0 && h`<div style=${css('padding:28px;text-align:center;font-size:17px;color:var(--ink-700)')}>No unprocessed trips for this filter.</div>`}
      </div>
      <div style=${css('display:flex;gap:18px;align-items:baseline;padding:8px 16px;border-top:2px solid var(--ink-300);background:var(--green-050)')}>
        ${inTotals.map(x => h`<span key=${x.k} style=${css('display:flex;flex-direction:column;gap:2px')}><span style=${css('font-size:13px;color:var(--ink-700)')}>${x.k}</span><span style=${css('font-size:' + x.size + ';color:var(--ink-900);font-variant-numeric:tabular-nums')}>${x.v}</span></span>`)}
      </div>
    </div>

    <div style=${css('flex:1;min-width:0;display:flex;flex-direction:column;border:2px solid var(--ink-300);border-radius:20px;overflow:hidden')}>
      <div style=${css('padding:10px 16px 6px;display:flex;align-items:center;gap:10px')}>
        ${badge(35, brown, '#fff', 'height:26px;font-size:14px')}
        <span style=${css('font-size:20px;color:var(--ink-900)')}>2. What came out, in kg.</span>
      </div>
      <div style=${css('flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;padding:0 16px')}>
        ${outRows.map(o => h`
          <div key=${o.key} style=${css('display:flex;align-items:center;justify-content:space-between;gap:12px;padding:4px 0 4px ' + o.indent + ';border-bottom:1px solid var(--ink-200)')}>
            <span style=${css('display:flex;flex-direction:column;gap:2px')}>
              <span style=${css('font-size:' + o.size + ';color:var(--ink-900)')}>${o.label}</span>
              ${o.isGroup && h`<button onClick=${() => setRec({expand:!R.expand})} style=${css('align-self:flex-start;border:none;background:none;padding:0;font-size:14px;color:var(--green-700);font-weight:700;cursor:pointer')}>${R.expand ? 'Hide materials' : 'Show 7 materials'}</button>`}
            </span>
            ${o.isInput && h`<${Input} type="number" placeholder="0" value=${o.val} onChange=${o.onChange} inputStyle=${kgInput} style=${{width:'150px'}} />`}
            ${o.isGroup && h`<span style=${css('font-size:20px;color:var(--ink-900);font-variant-numeric:tabular-nums;padding-right:14px')}>${o.sum}</span>`}
          </div>`)}
      </div>
      <div style=${css('display:flex;gap:10px;padding:8px 16px;border-top:1px solid var(--ink-200)')}>
        <div style=${css('flex:1;border-radius:16px;background:var(--green-050);padding:6px 12px;display:flex;flex-direction:column;gap:0')}>
          <span style=${css('font-size:13px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:var(--green-700)')}>Recovered</span>
          <span style=${css('font-size:28px;line-height:1.1;color:var(--ink-900)')}>${input>0 ? Math.round(recovered/input*100) + '%' : '—'}</span>
        </div>
        <div style=${css('flex:1;border-radius:16px;background:var(--ink-050);padding:6px 12px;display:flex;flex-direction:column;gap:0')}>
          <span style=${css('font-size:13px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:var(--ink-700)')}>Not accounted</span>
          <span style=${css('font-size:28px;line-height:1.1;color:var(--ink-900)')}>${input>0 ? kg(input - allOut) : '—'}</span>
        </div>
      </div>
      <div style=${css('padding:0 16px 12px;display:flex;flex-direction:column;gap:6px')}>
        ${(R.msg || R.err) && h`<div style=${css('font-size:16px;color:' + (R.err ? '#C62828' : 'var(--green-700)') + ';font-weight:700')}>${R.err || R.msg}</div>`}
        <${Button} size="lg" disabled=${!(chosen.length>0 && allOut>0)} onClick=${saveBatch} style=${{width:'100%', justifyContent:'center', padding:'12px 24px', fontSize:'20px', whiteSpace:'nowrap'}}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:32px;height:30px;padding:0 7px;border-radius:999px;background:#7B4A1F;box-shadow:0 0 0 2px #fff;color:#fff;font-size:16px')}>36</span>Save batch<//>
      </div>
    </div>
  </div>
</div>`;
  }

  // --- 6 reports -------------------------------------------------------------
  renderRep() {
    const s = this.state, RP = s.rep, data = RP.data, OR = '#E0620B';
    const pickView = id => { this.setState(st => ({rep:{...st.rep, view:id, data:null, msg:null, file:null}})); this.loadReport({view:id}); };
    const setRep = patch => { this.setState(st => ({rep:{...st.rep, ...patch, msg:null, file:null}})); this.loadReport(patch); };
    const incN = s.srv.pending.length;
    const repTabs = [['daily',61,'Daily summary'],['shift',62,'Shift summary'],['custom',63,'Hourly, weekly, monthly'],['inc',64,'Incomplete · ' + incN]].map(([id,code,label]) => {
      const on = RP.view===id;
      return {id, code, label, border: on ? OR : 'var(--ink-300)', bg: on ? OR : '#fff', fg: on ? '#fff' : 'var(--ink-900)', bBg: on ? '#fff' : OR, bFg: on ? OR : '#fff'};
    });
    const tripsTxt = n => n ? n + (n===1 ? ' trip' : ' trips') : '—';
    const netTxt = (n, t) => t ? kg(n) : '—';
    const segBtn = (o, on, pick, hgt) => { const sl = SEL(on); return h`<button key=${o} onClick=${pick} style=${css('height:' + (hgt||40) + 'px;padding:0 14px;border-radius:999px;border:2px solid ' + sl.border + ';background:' + sl.bg + ';font-size:' + (hgt ? 15 : 16) + 'px;font-weight:' + sl.weight + ';color:' + sl.fg + ';cursor:pointer;white-space:nowrap')}>${o}</button>`; };
    const box = (code, label, body) => h`<div style=${css('display:flex;flex-direction:column;gap:6px;padding:8px 10px;border:2px solid var(--ink-300);border-radius:14px')}><span style=${css('display:flex;align-items:center;gap:8px;font-size:14px;font-weight:700;color:var(--ink-900)')}>${badge(code, OR, '#fff')}${label}</span>${body}</div>`;
    const dateInput = (val, key) => h`<input type="date" value=${val} onChange=${e => setRep({[key]:e.target.value})} style=${css('height:40px;padding:0 10px;border-radius:10px;border:2px solid var(--ink-300);font-family:var(--font-body);font-size:16px;color:var(--ink-900)')} />`;

    let body = null;
    if (RP.view === 'daily' && data && data.in) {
      const cards = [{n:1, title:'Inward', headBg:C[1], d:data.in}, {n:2, title:'Outward', headBg:C[2], d:data.out}];
      body = h`
    <div style=${css('flex:1;min-height:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px')}>
      ${cards.map(c => h`
        <div key=${c.n} style=${css('display:flex;flex-direction:column;border:2px solid var(--ink-300);border-radius:18px;overflow:hidden;min-height:0')}>
          <div style=${css('display:flex;align-items:center;gap:16px;padding:10px 16px;background:' + c.headBg + ';color:#fff')}>
            <span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:26px;padding:0 7px;border-radius:999px;background:#fff;color:' + c.headBg + ';font-weight:700;font-size:13px')}>${c.n}</span>
            <span style=${css('font-size:20px;font-weight:700')}>${c.title}</span>
            <span style=${css('margin-left:auto;display:flex;align-items:baseline;gap:16px;white-space:nowrap')}><span style=${css('font-size:16px')}>${tripsTxt(c.d.total.trips)}</span>${c.d.total.inc>0 && h`<span style=${css('font-size:14px;padding:2px 10px;border-radius:999px;background:#fff;color:#151515;font-weight:700')}>${c.d.total.inc + ' incomplete'}</span>`}<span style=${css('font-size:26px;font-weight:700')}>${kg(c.d.total.net)}</span></span>
          </div>
          <div style=${css('display:grid;grid-template-columns:minmax(0,1fr) 64px 104px 120px;gap:8px;padding:6px 16px;background:var(--ink-100);font-size:13px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:var(--ink-700)')}><span>Material</span><span style=${css('text-align:right')}>Trips</span><span style=${css('text-align:right')}>Incomplete</span><span style=${css('text-align:right')}>Net</span></div>
          <div style=${css('flex:1;min-height:0;overflow-y:auto')}>
            ${c.d.rows.map(r => h`
              <div key=${r.label} style=${css('display:grid;grid-template-columns:minmax(0,1fr) 64px 104px 120px;gap:8px;align-items:center;padding:6px 16px;border-bottom:1px solid var(--ink-200)')}>
                <span style=${css('font-size:18px;color:var(--ink-900)')}>${r.label}</span>
                <span style=${css('font-size:18px;color:var(--ink-900);text-align:right;font-variant-numeric:tabular-nums')}>${r.trips || '—'}</span>
                <span style=${css('text-align:right')}>${r.inc>0 && h`<span style=${css('padding:2px 10px;border-radius:999px;background:#151515;color:#fff;font-size:14px;font-weight:700')}>${r.inc}</span>`}</span>
                <span style=${css('font-size:18px;color:var(--ink-900);text-align:right;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap')}>${netTxt(r.net, r.trips)}</span>
              </div>`)}
          </div>
        </div>`)}
    </div>`;
    } else if (RP.view === 'shift' && data && data.shifts) {
      const SH = data.shifts, starts = SH.starts.slice(0, SH.count);
      const saveShifts = v => api('set_shifts', v).then(() => this.loadReport()).catch(e => this.setState(st => ({rep:{...st.rep, msg:e.message}})));
      const shiftCountSeg = ['2 shifts','3 shifts'].map(o => segBtn(o, Number(o[0])===SH.count, () => saveShifts({count:Number(o[0]), starts: Number(o[0])===2 && SH.count===3 && SH.starts[1]==='14:00' ? [SH.starts[0], '18:00', SH.starts[2]] : SH.starts}), 38));
      const cols = 'minmax(0,1.2fr) repeat(' + starts.length + ',minmax(0,1fr))';
      body = h`
    <${React.Fragment}>
    <div style=${css('display:flex;align-items:center;gap:14px;padding:8px 12px;border:2px solid var(--ink-300);border-radius:14px;flex-wrap:wrap')}>
      <span style=${css('display:flex;align-items:center;gap:8px;font-size:15px;font-weight:700;color:var(--ink-900);white-space:nowrap')}>${badge(60, OR, '#fff')}Shift times</span>
      <div style=${css('display:flex;gap:6px')}>${shiftCountSeg}</div>
      ${starts.map((st,i) => h`<label key=${i} style=${css('display:flex;align-items:center;gap:6px;font-size:15px;color:var(--ink-900);white-space:nowrap')}>${'Shift ' + (i+1) + ' starts'}<input type="time" value=${st} onChange=${e => { const ns = [...SH.starts]; ns[i] = e.target.value; saveShifts({count:SH.count, starts:ns}); }} style=${css('height:38px;padding:0 8px;border-radius:10px;border:2px solid var(--ink-300);font-family:var(--font-body);font-size:16px;color:var(--ink-900)')} /></label>`)}
      <span style=${css('margin-left:auto;font-size:14px;color:var(--ink-700);white-space:nowrap')}>A trip counts in the shift its time falls in. Saved as default.</span>
    </div>
    <div style=${css('flex:1;min-height:0;display:flex;flex-direction:column;border:2px solid var(--ink-300);border-radius:18px;overflow:hidden')}>
      <div style=${css('display:grid;grid-template-columns:' + cols + ';gap:8px;padding:8px 16px;background:#151515;color:#fff')}>
        <span style=${css('font-size:15px;font-weight:700')}>Material</span>
        ${starts.map((st,i) => h`<span key=${i} style=${css('display:flex;flex-direction:column;align-items:flex-end;line-height:1.2')}><span style=${css('font-size:16px;font-weight:700')}>${'Shift ' + (i+1)}</span><span style=${css('font-size:13px;color:#CBD4CE')}>${st + ' – ' + starts[(i+1) % starts.length]}</span></span>`)}
      </div>
      <div style=${css('flex:1;min-height:0;overflow-y:auto')}>
        ${data.rows.map(r => h`
          <div key=${r.label} style=${css('display:grid;grid-template-columns:' + cols + ';gap:8px;align-items:center;padding:6px 16px;border-bottom:1px solid var(--ink-200);background:' + (r.total ? 'var(--ink-100)' : '#fff'))}>
            <span style=${css('display:flex;align-items:center;gap:8px;font-size:17px;color:var(--ink-900);font-weight:' + (r.total ? 700 : 400) + ';white-space:nowrap;min-width:0')}><span style=${css('width:10px;height:10px;border-radius:50%;background:' + C[r.dir==='in'?1:2] + ';flex:none')}></span><span style=${css('white-space:nowrap')}>${r.label}</span></span>
            ${r.cells.map((c,i) => h`<span key=${i} style=${css('display:flex;align-items:baseline;justify-content:flex-end;gap:10px;white-space:nowrap;font-variant-numeric:tabular-nums')}><span style=${css('font-size:14px;color:var(--ink-700)')}>${c.trips ? tripsTxt(c.trips) : ''}</span>${c.inc>0 && h`<span style=${css('font-size:12px;padding:1px 8px;border-radius:999px;background:#151515;color:#fff;font-weight:700')}>${'+' + c.inc + ' inc.'}</span>`}<span style=${css('font-size:17px;color:var(--ink-900);font-weight:700')}>${netTxt(c.net, c.trips)}</span></span>`)}
          </div>`)}
      </div>
    </div>
    <//>`;
    } else if (RP.view === 'inc' && data && data.rows) {
      const cols = 'grid-template-columns:150px minmax(0,1fr) 150px 120px 120px 190px';
      body = h`
    <${React.Fragment}>
    <div style=${css('font-size:16px;color:var(--ink-900)')}>A record is complete when it has both gross and tare. These still need an empty weight, so their net is not counted in any summary.</div>
    <div style=${css('flex:1;min-height:0;display:flex;flex-direction:column;border:2px solid var(--ink-300);border-radius:18px;overflow:hidden')}>
      <div style=${css('display:grid;' + cols + ';gap:8px;padding:8px 16px;background:#151515;color:#fff;font-size:15px;font-weight:700')}>
        <span>Ticket</span><span>Vehicle</span><span>In at</span><span style=${css('text-align:right')}>Gross</span><span style=${css('text-align:right')}>Tare</span><span></span>
      </div>
      <div style=${css('flex:1;min-height:0;overflow-y:auto')}>
        ${data.rows.map(r => h`
          <div key=${r.id} style=${css('display:grid;' + cols + ';gap:8px;align-items:center;padding:8px 16px;border-bottom:1px solid var(--ink-200);font-size:17px;color:var(--ink-900);font-variant-numeric:tabular-nums')}>
            <span style=${css('font-weight:700')}>${r.id}</span><span>${r.vno}</span><span>${shortDay(r.time.slice(0,10)) + ' ' + r.time.slice(11)}</span><span style=${css('text-align:right;font-weight:700')}>${kg(r.gross)}</span>
            <span style=${css('justify-self:end;padding:2px 10px;border-radius:999px;background:#151515;color:#fff;font-size:14px;font-weight:700')}>Pending</span>
            <button onClick=${() => this.goTare(r.vno)} style=${css('justify-self:end;display:flex;align-items:center;gap:6px;height:40px;padding:0 14px 0 5px;border-radius:999px;border:2px solid #151515;background:#F2C200;color:#151515;font-size:15px;font-weight:700;cursor:pointer;white-space:nowrap')}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:28px;border-radius:999px;background:#151515;color:#F2C200;font-size:14px')}>4</span>Weigh empty</button>
          </div>`)}
        ${data.rows.length===0 && h`<div style=${css('padding:24px;font-size:18px;color:var(--ink-700);text-align:center')}>All records are complete.</div>`}
      </div>
    </div>
    <//>`;
    } else if (RP.view === 'custom') {
      const rows = (data && data.rows) || [];
      const showIn = RP.dir!=='Outward', showOut = RP.dir!=='Inward';
      const head = RP.period==='Hourly' ? 'Hour' : RP.period==='Daily' ? 'Day' : RP.period==='Weekly' ? 'Week' : 'Month';
      const download = () => api('export_csv', {period:RP.period, dateFrom:RP.from, dateTo:RP.to, dir:RP.dir})
        .then(r => this.setState(st => ({rep:{...st.rep, file:r, msg:null}}))).catch(e => this.setState(st => ({rep:{...st.rep, msg:e.message}})));
      const cols = 'grid-template-columns:minmax(0,1.4fr) repeat(3,minmax(0,1fr))';
      body = h`
    <${React.Fragment}>
    <div style=${css('display:flex;align-items:stretch;gap:10px;flex-wrap:wrap')}>
      ${box(65, 'Summary by', h`<div style=${css('display:flex;gap:6px')}>${['Hourly','Daily','Weekly','Monthly'].map(o => segBtn(o, RP.period===o, () => setRep({period:o})))}</div>`)}
      ${box(66, 'From', dateInput(RP.from, 'from'))}
      ${box(67, 'To', dateInput(RP.to, 'to'))}
      ${box(68, 'Show', h`<div style=${css('display:flex;gap:6px')}>${['Both','Inward','Outward'].map(o => segBtn(o, RP.dir===o, () => setRep({dir:o})))}</div>`)}
      <div style=${css('margin-left:auto;display:flex;align-items:flex-end')}>
        <${Button} size="lg" onClick=${download} style=${{whiteSpace:'nowrap'}}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:32px;height:30px;padding:0 7px;border-radius:999px;background:#E0620B;box-shadow:0 0 0 2px #fff;color:#fff;font-size:15px')}>69</span>Download<//>
      </div>
    </div>
    <div style=${css('flex:1;min-height:0;display:flex;flex-direction:column;border:2px solid var(--ink-300);border-radius:18px;overflow:hidden')}>
      <div style=${css('display:grid;' + cols + ';gap:8px;padding:8px 16px;background:#151515;color:#fff;font-size:15px;font-weight:700')}>
        <span>${head}</span><span style=${css('text-align:right')}>Trips</span><span style=${css('text-align:right')}>Inward net</span><span style=${css('text-align:right')}>Outward net</span>
      </div>
      <div style=${css('flex:1;min-height:0;overflow-y:auto')}>
        ${rows.map(r => h`
          <div key=${r.label} style=${css('display:grid;' + cols + ';gap:8px;align-items:center;padding:6px 16px;border-bottom:1px solid var(--ink-200);font-size:17px;color:var(--ink-900);font-variant-numeric:tabular-nums')}>
            <span>${r.label}</span><span style=${css('text-align:right')}>${fmt(r.trips)}</span><span style=${css('text-align:right;font-weight:700;white-space:nowrap')}>${showIn ? kg(r.in_net) : '—'}</span><span style=${css('text-align:right;font-weight:700;white-space:nowrap')}>${showOut ? kg(r.out_net) : '—'}</span>
          </div>`)}
        ${data && rows.length===0 && h`<div style=${css('padding:24px;font-size:18px;color:var(--ink-700);text-align:center')}>No complete records in these dates.</div>`}
      </div>
      <div style=${css('display:flex;align-items:center;gap:12px;padding:8px 16px;border-top:2px solid var(--ink-300);font-size:15px;color:var(--ink-700)')}>
        ${RP.file ? h`<${React.Fragment}><span style=${css('color:var(--green-700);font-weight:700;flex:none')}>Saved.</span><span style=${css('flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis')}>${RP.file.path}</span><button onClick=${() => api('open_folder', {path:RP.file.folder}).catch(() => {})} style=${css('flex:none;height:32px;padding:0 14px;border-radius:999px;border:2px solid var(--green-600);background:#fff;color:var(--green-700);font-size:14px;font-weight:700;cursor:pointer')}>Open folder</button><//>`
          : rows.length + ' rows · Net is from complete records only. Download saves this table as a CSV file for Excel, plus one with every trip.'}
      </div>
    </div>
    <//>`;
    }
    const repDate = RP.view==='custom' || RP.view==='inc' ? '' : 'Today · ' + new Date().toLocaleDateString('en-IN',{day:'2-digit', month:'short', year:'numeric'});
    return h`
<div data-screen-label="6 Reports" style=${css('flex:1;min-width:0;display:flex;flex-direction:column;gap:12px;padding:14px 24px 16px')}>
  <div style=${css('display:flex;align-items:center;gap:10px')}>
    ${repTabs.map(r => h`<button key=${r.id} onClick=${() => pickView(r.id)} style=${css('display:flex;align-items:center;gap:8px;height:48px;padding:0 16px 0 7px;border-radius:999px;border:2px solid ' + r.border + ';background:' + r.bg + ';color:' + r.fg + ';font-size:16px;font-weight:700;cursor:pointer;white-space:nowrap')}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:30px;padding:0 7px;border-radius:999px;background:' + r.bBg + ';color:' + r.bFg + ';font-size:14px')}>${r.code}</span>${r.label}</button>`)}
    <span style=${css('margin-left:auto;font-size:17px;color:var(--ink-900);font-weight:700;white-space:nowrap')}>${repDate}</span>
  </div>
  ${RP.msg && h`<div style=${css('font-size:16px;color:#C62828;font-weight:700')}>${RP.msg}</div>`}
  ${body || h`<div style=${css('padding:24px;font-size:18px;color:var(--ink-700)')}>Loading…</div>`}
</div>`;
  }

  // --- 5 sync ------------------------------------------------------------------
  renderSync() {
    const s = this.state, srv = s.srv, mode = s.live.sync.state, qn = s.live.sync.queued;
    const syncCard = mode==='synced' ? {bg:'#E4F6E9', fg:'#0E5230', kicker:'Online', title:'All synced.', text:'Every entry and photo is on the server.'}
      : mode==='error' ? {bg:'#FDECEC', fg:RED, kicker:'Sync error', title:'The server did not answer.', text:'Entries are safe on this computer. Try again, or call support and say “black 51”.'}
      : mode==='off' ? {bg:'#E8EDEA', fg:'#151515', kicker:'Sync off', title:'Sync is not set up.', text:'Keep working. Entries are saved on this computer. Ask the admin to set up sync, then they send by themselves.'}
      : {bg:'#E8EDEA', fg:'#151515', kicker:'Offline', title:'No internet right now.', text:'Keep working. Entries are saved on this computer and send by themselves when the internet is back.'};
    const queueRows = srv.queue.map((q, i) => ({...q, key:i, status: mode==='error' || q.failed ? 'Failed' : 'Queued', bg: mode==='error' || q.failed ? RED : '#E8EDEA', fg: mode==='error' || q.failed ? '#fff' : '#151515'}));
    const retry = () => {
      this.setState({retrying:true, retryMsg:null});
      api('retry_sync').then(r => {
        this.setState({retrying:false, retryMsg: r.state==='synced' ? (r.queued ? 'Sent what it could.' : 'Everything is sent.') : r.state==='error' ? 'Server still not answering.' : r.state==='off' ? 'Sync is not set up.' : 'Still no internet. Your entries are safe.'});
        this.refresh(); this.pollLive();
      }).catch(e => this.setState({retrying:false, retryMsg:e.message}));
    };
    return h`
<div data-screen-label="5 Sync" style=${css('flex:1;min-width:0;display:flex;gap:18px;padding:16px 24px')}>
  <div style=${css('width:400px;flex:none;border-radius:24px;background:' + syncCard.bg + ';padding:24px;display:flex;flex-direction:column;gap:10px')}>
    <span style=${css('font-size:13px;letter-spacing:0.14em;text-transform:uppercase;font-weight:700;color:' + syncCard.fg)}>${syncCard.kicker}</span>
    <span style=${css('font-size:44px;line-height:1.08;letter-spacing:-0.015em;color:var(--ink-900)')}>${syncCard.title}</span>
    <span style=${css('font-size:19px;line-height:1.45;color:var(--ink-700)')}>${syncCard.text}</span>
    <div style=${css('display:flex;align-items:baseline;gap:10px;margin-top:8px')}>
      <span style=${css('font-size:72px;line-height:1;color:var(--ink-900)')}>${qn}</span>
      <span style=${css('font-size:20px;color:var(--ink-700)')}>waiting to send</span>
    </div>
    <div style=${css('flex:1')}></div>
    ${s.retryMsg && h`<div style=${css('font-size:16px;font-weight:700;color:var(--ink-900)')}>${s.retryMsg}</div>`}
    <${Button} size="lg" disabled=${s.retrying} onClick=${retry} style=${{width:'100%', justifyContent:'center', padding:'18px 28px', fontSize:'22px', whiteSpace:'nowrap'}}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:32px;height:30px;padding:0 7px;border-radius:999px;background:#151515;box-shadow:0 0 0 2px #fff;color:#fff;font-size:16px')}>51</span>${s.retrying ? 'Trying…' : 'Retry now'}<//>
  </div>
  <div style=${css('flex:1;min-width:0;display:flex;flex-direction:column;gap:18px')}>
    <div style=${css('display:flex;flex-direction:column;border:2px solid var(--ink-300);border-radius:20px;overflow:hidden;max-height:210px')}>
      <div style=${css('padding:8px 16px;font-size:19px;color:var(--ink-900);border-bottom:1px solid var(--ink-200)')}>Waiting to send</div>
      <div style=${css('overflow-y:auto;overflow-x:hidden;min-height:0')}>
        ${queueRows.map(q => h`
          <div key=${q.key} style=${css('display:grid;grid-template-columns:116px minmax(0,1fr) 50px 70px;gap:6px;align-items:center;padding:7px 14px;border-bottom:1px solid var(--ink-200)')}>
            <span style=${css('font-size:16px;font-weight:700;color:var(--ink-900);white-space:nowrap;overflow:hidden;text-overflow:ellipsis')}>${q.id}</span>
            <span style=${css('font-size:16px;color:var(--ink-700)')}>${q.what}</span>
            <span style=${css('font-size:15px;color:var(--ink-700)')}>${q.time}</span>
            <span style=${css('justify-self:end;padding:3px 12px;border-radius:999px;background:' + q.bg + ';color:' + q.fg + ';font-size:13px;font-weight:700')}>${q.status}</span>
          </div>`)}
        ${queueRows.length===0 && h`<div style=${css('padding:22px;font-size:17px;color:var(--ink-700)')}>Nothing waiting. Everything is on the server.</div>`}
      </div>
    </div>
    <div style=${css('flex:1;min-height:0;display:flex;flex-direction:column;border:2px solid var(--ink-300);border-radius:20px;overflow:hidden')}>
      <div style=${css('padding:8px 16px;font-size:19px;color:var(--ink-900);border-bottom:1px solid var(--ink-200)')}>Today's entries</div>
      <div style=${css('overflow-y:auto;overflow-x:hidden;min-height:0')}>
        ${srv.today.map(e => h`
          <div key=${e.id} style=${css('display:grid;grid-template-columns:116px minmax(0,1fr) 100px 170px;gap:6px;align-items:center;padding:6px 14px;border-bottom:1px solid var(--ink-200)')}>
            <span style=${css('font-size:16px;font-weight:700;color:var(--ink-900)')}>${e.id}</span>
            <span style=${css('font-size:16px;color:var(--ink-700);white-space:nowrap;overflow:hidden;text-overflow:ellipsis')}>${e.what}</span>
            <span style=${css('font-size:16px;color:var(--ink-900);text-align:right')}>${e.net==null ? 'Tare pending' : kg(e.net)}</span>
            <span style=${css('justify-self:end')}>
              ${!e.asked && h`<button onClick=${() => this.setState({corr:{open:true, id:e.id, reason:'', err:null}})} style=${css('display:flex;align-items:center;gap:6px;height:38px;padding:0 14px 0 5px;border-radius:999px;border:1px solid var(--green-600);background:#fff;color:var(--green-700);font-size:15px;font-weight:700;cursor:pointer;white-space:nowrap')}><span style=${css('display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:26px;border-radius:999px;background:#151515;color:#fff;font-size:13px')}>52</span>Ask to correct</button>`}
              ${e.asked && h`<span style=${css('padding:5px 12px;border-radius:999px;background:#F2C200;color:#151515;font-size:14px;font-weight:700;white-space:nowrap')}>Waiting for admin</span>`}
            </span>
          </div>`)}
        ${srv.today.length===0 && h`<div style=${css('padding:22px;font-size:17px;color:var(--ink-700)')}>No entries yet today.</div>`}
      </div>
    </div>
  </div>
</div>`;
  }

  // --- dialogs -----------------------------------------------------------------
  renderDialogs() {
    const s = this.state, C2 = s.corr, S = s.sample;
    const corrChips = ['Wrong vehicle number','Wrong waste type','Wrong source','Wrong material'].map(l => ({label:l, ...SEL(C2.reason===l)}));
    const sk = Number(S.kg)||0;
    const pct = x => sk>0 && x ? Math.round(Number(x)/sk*100) + '% of sample' : ' ';
    const setS = x => e => { const val = e.target.value; this.setState(st => ({sample:{...st.sample, [x]:val, err:null}})); };
    const sampleFields = [['kg','Sample weight (kg)'],['wet','Wet part (kg)'],['dry','Dry part (kg)'],['inert','Inert part (kg)']].map(([x,label]) => ({x, label, val:S[x], onChange:setS(x), pct: x==='kg' ? 'Whole sample' : pct(S[x])}));
    const closeCorr = () => this.setState(st => ({corr:{...st.corr, open:false}}));
    const sendCorr = () => api('ask_correction', {id:C2.id, reason:C2.reason}).then(() => { closeCorr(); this.refresh(); }).catch(e => this.setState(st => ({corr:{...st.corr, err:e.message}})));
    const closeSample = () => this.setState(st => ({sample:{...st.sample, open:false}}));
    const saveSample = () => api('save_sample', {kg:S.kg, wet:S.wet, dry:S.dry, inert:S.inert})
      .then(() => { this.setState(st => ({sample:{open:false, kg:'', wet:'', dry:'', inert:'', err:null}, rec:{...st.rec, msg:'Mixed sample saved for ' + st.srv.month + '.', err:null}})); this.refresh(); })
      .catch(e => this.setState(st => ({sample:{...st.sample, err:e.message}})));
    return h`
<${React.Fragment}>
<${Dialog} open=${C2.open} title=${'Ask to correct ' + (C2.id||'')} onClose=${closeCorr} width=${560}>
  <div style=${css('display:flex;flex-direction:column;gap:14px')}>
    <span>Saved entries cannot be changed here. The site admin checks your request and keeps the old version.</span>
    <div style=${css('display:flex;flex-wrap:wrap;gap:8px')}>
      ${corrChips.map(c => h`<button key=${c.label} onClick=${() => this.setState(st => ({corr:{...st.corr, reason:c.label, err:null}}))} style=${css('height:42px;padding:0 16px;border-radius:999px;border:2px solid ' + c.border + ';background:' + c.bg + ';font-size:15px;color:' + c.fg + ';cursor:pointer')}>${c.label}</button>`)}
    </div>
    <${Input} label="What is wrong? (required)" placeholder="Say what should change" value=${C2.reason} onChange=${e => { const val = e.target.value; this.setState(st => ({corr:{...st.corr, reason:val, err:null}})); }} error=${C2.err || undefined} />
    <div style=${css('display:flex;justify-content:flex-end;gap:10px;margin-top:6px')}>
      <${Button} variant="ghost" onClick=${closeCorr}>Cancel<//>
      <${Button} disabled=${!C2.reason.trim()} onClick=${sendCorr}>Send to admin<//>
    </div>
  </div>
<//>

<${Dialog} open=${S.open} title=${'Mixed sample for ' + s.srv.month} onClose=${closeSample} width=${600}>
  <div style=${css('display:flex;flex-direction:column;gap:14px')}>
    <span>Weigh one sample of mixed waste on the small scale. Then sort it and weigh each part.</span>
    <div style=${css('display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px')}>
      ${sampleFields.map(f => h`<${Input} key=${f.x} label=${f.label} type="number" placeholder="0" value=${f.val} onChange=${f.onChange} helper=${f.pct} />`)}
    </div>
    ${S.err && h`<div style=${css('font-size:15px;color:#C62828;font-weight:700')}>${S.err}</div>`}
    <div style=${css('display:flex;justify-content:flex-end;gap:10px;margin-top:6px')}>
      <${Button} variant="ghost" onClick=${closeSample}>Cancel<//>
      <${Button} disabled=${!(sk>0 && Number(S.wet)+Number(S.dry)+Number(S.inert) > 0)} onClick=${saveSample}>Save sample<//>
    </div>
  </div>
<//>
${this.renderAdmin()}
<//>`;
  }

  // --- admin settings (not in the prototype; kept plain) ------------------------
  renderAdmin() {
    const A = this.state.admin;
    if (!A.open) return null;
    const setA = patch => this.setState(st => ({admin:{...st.admin, ...patch}}));
    const close = () => setA({open:false, pin:'', view:null, draft:null, ops:null, err:null, msg:null});
    if (!A.view) {
      const go = () => api('admin_login', {pin:A.pin}).then(view => setA({view, draft:JSON.parse(JSON.stringify(view.settings)), ops:view.settings.operators.map(o => ({name:o.name, pin:'', has:o.has_pin})), counters:{...view.counters}, newAdminPin:'', err:null, msg:null}))
        .catch(e => setA({err:e.message, pin:''}));
      return h`
<${Dialog} open=${true} title="Admin settings" onClose=${close} width=${420}>
  <div style=${css('display:flex;flex-direction:column;gap:14px')}>
    <${Input} label="Admin PIN" type="password" inputMode="numeric" maxLength=${4} value=${A.pin} autoFocus=${true} onChange=${e => setA({pin:e.target.value.replace(/\D/g,'').slice(0,4), err:null})} onKeyDown=${e => { if (e.key==='Enter') go(); }} error=${A.err || undefined} helper="First time? It is 0000. Change it below after you sign in." />
    <div style=${css('display:flex;justify-content:flex-end;gap:10px')}>
      <${Button} variant="ghost" onClick=${close}>Cancel<//>
      <${Button} disabled=${A.pin.length!==4} onClick=${go}>Open<//>
    </div>
  </div>
<//>`;
    }
    const d = A.draft, live = A.view.live;
    const upd = (path, val) => { const nd = JSON.parse(JSON.stringify(d)); let o = nd; path.slice(0,-1).forEach(k => { o = o[k]; }); o[path[path.length-1]] = val; setA({draft:nd, msg:null, err:null}); };
    const row = (label, path, type, opts) => {
      const val = path.reduce((o,k) => o == null ? o : o[k], d);
      const onChange = e => upd(path, type==='number' ? (e.target.value === '' ? '' : Number(e.target.value)) : type==='check' ? e.target.checked : e.target.value);
      if (type === 'select') return h`<label class="admin-row">${label}<select value=${val} onChange=${onChange}>${opts.map(o => h`<option key=${o} value=${o}>${o}</option>`)}</select></label>`;
      if (type === 'check') return h`<label style=${css('display:flex;align-items:center;gap:10px;font-size:15px;font-weight:700;color:var(--ink-900)')}><input type="checkbox" checked=${!!val} onChange=${onChange} style=${{width:'20px', height:'20px'}} />${label}</label>`;
      return h`<label class="admin-row">${label}<input type=${type||'text'} value=${val == null ? '' : val} onChange=${onChange} list=${opts ? 'dl-' + path.join('-') : undefined} />${opts && h`<datalist id=${'dl-' + path.join('-')}>${opts.map(o => h`<option key=${o} value=${o} />`)}</datalist>`}</label>`;
    };
    const wbLive = live.wb;
    const camBox = name => h`
      <div class="admin-sec">
        <h4>${name==='front' ? 'Front camera' : 'Back camera'}</h4>
        ${live.cams[name] && live.cams[name].live ? h`<img class="admin-thumb" src=${camUrl(name)} alt="" />` : h`<div class="admin-thumb">${(live.cams[name] && live.cams[name].error) || 'No signal'}</div>`}
        <div class="admin-grid">
          ${row('Type', ['cameras', name, 'type'], 'select', ['USB','RTSP','HTTP','None'])}
          ${row('USB number', ['cameras', name, 'index'], 'number')}
        </div>
        ${row('RTSP or HTTP address', ['cameras', name, 'url'])}
      </div>`;
    const ops = A.ops;
    const save = () => api('admin_save', {patch:{site_name:d.site_name, agency_name:d.agency_name, weighbridge:d.weighbridge, cameras:d.cameras, cloud:d.cloud, reports_folder:d.reports_folder},
        operators: ops.map(o => ({name:o.name, pin:o.pin})), adminPin: A.newAdminPin || null, counters: A.counters})
      .then(view => { setA({view, draft:JSON.parse(JSON.stringify(view.settings)), ops:view.settings.operators.map(o => ({name:o.name, pin:'', has:o.has_pin})), counters:{...view.counters}, newAdminPin:'', msg:'Saved.', err:null}); api('boot').then(boot => this.setState({boot})); this.refresh(); })
      .catch(e => setA({err:e.message, msg:null}));
    const refreshLive = () => api('admin_view').then(view => setA({view})).catch(e => setA({err:e.message}));
    return h`
<${Dialog} open=${true} title="Admin settings" onClose=${close} width=${980}>
  <div style=${css('display:flex;flex-direction:column;gap:12px;max-height:400px;overflow-y:auto;padding-right:6px')}>
    <div class="admin-grid">
      <div class="admin-sec">
        <h4>Site</h4>
        ${row('Site name', ['site_name'])}
        ${row('Company', ['agency_name'])}
        ${row('Reports folder (empty = inside data folder)', ['reports_folder'])}
        <span style=${css('font-size:13px;color:var(--ink-700)')}>${'Data folder: ' + A.view.dataFolder}</span>
      </div>
      <div class="admin-sec">
        <h4>Operators and PINs</h4>
        ${ops.map((o,i) => h`<div key=${i} style=${css('display:grid;grid-template-columns:minmax(0,1fr) 120px 36px;gap:8px;align-items:end')}>
          <label class="admin-row">Name<input value=${o.name} onChange=${e => { const n = ops.slice(); n[i] = {...o, name:e.target.value}; setA({ops:n}); }} /></label>
          <label class="admin-row">${o.has ? 'New PIN' : 'PIN (now 0000)'}<input inputMode="numeric" maxLength=${4} value=${o.pin} onChange=${e => { const n = ops.slice(); n[i] = {...o, pin:e.target.value.replace(/\D/g,'').slice(0,4)}; setA({ops:n}); }} /></label>
          <button onClick=${() => setA({ops: ops.filter((_,j) => j!==i)})} title="Remove" style=${css('height:38px;border-radius:10px;border:2px solid var(--ink-300);background:#fff;cursor:pointer;font-size:18px')}>×</button>
        </div>`)}
        <div style=${css('display:flex;gap:10px;align-items:end')}>
          <${Button} variant="secondary" size="sm" onClick=${() => setA({ops:[...ops, {name:'', pin:'', has:false}]})}>Add operator<//>
          <label class="admin-row" style=${{marginLeft:'auto', width:'160px'}}>New admin PIN<input inputMode="numeric" maxLength=${4} value=${A.newAdminPin} onChange=${e => setA({newAdminPin:e.target.value.replace(/\D/g,'').slice(0,4)})} /></label>
        </div>
      </div>
    </div>
    <div class="admin-sec">
      <h4>Weighbridge</h4>
      <div style=${css('display:flex;align-items:center;gap:14px;font-size:15px;color:var(--ink-900)')}>
        <span style=${css('padding:3px 12px;border-radius:999px;font-weight:700;color:#fff;background:' + (wbLive.connected ? GRN : RED))}>${wbLive.connected ? 'Reading ' + fmt(wbLive.weight) + ' kg' + (wbLive.stable ? ' · stable' : ' · settling') : 'Not connected'}</span>
        <span style=${css('color:var(--ink-700)')}>${wbLive.error || ''}</span>
        <${Button} variant="secondary" size="sm" onClick=${refreshLive}>Check again<//>
      </div>
      ${row('Simulate weighbridge (testing only — no real weights)', ['weighbridge','simulate'], 'check')}
      <div style=${css('display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px 14px')}>
        ${row('COM port', ['weighbridge','com_port'], 'text', A.view.ports)}
        ${row('Baud rate', ['weighbridge','baud_rate'], 'select', [1200,2400,4800,9600,19200,38400,57600,115200])}
        ${row('Data bits', ['weighbridge','data_bits'], 'select', [7,8])}
        ${row('Parity', ['weighbridge','parity'], 'select', ['None','Odd','Even','Mark','Space'])}
        ${row('Stop bits', ['weighbridge','stop_bits'], 'select', [1,1.5,2])}
        ${row('Weight pattern (regex)', ['weighbridge','regex_pattern'])}
        ${row('Multiplier', ['weighbridge','weight_multiplier'], 'number')}
        ${row('Steady within (kg)', ['weighbridge','stable_tolerance_kg'], 'number')}
        ${row('Steady for (seconds)', ['weighbridge','stable_seconds'], 'number')}
        ${row('Least weight to save (kg)', ['weighbridge','min_weight_kg'], 'number')}
      </div>
    </div>
    <div class="admin-grid">${camBox('front')}${camBox('back')}</div>
    <div class="admin-grid">
      <div class="admin-sec">
        <h4>Sync to Google Cloud</h4>
        ${row('Turn on sync', ['cloud','enabled'], 'check')}
        ${row('Bucket name', ['cloud','bucket_name'])}
        ${row('Service account key file (full path to .json)', ['cloud','credentials_path'])}
      </div>
      <div class="admin-sec">
        <h4>Ticket serials</h4>
        <span style=${css('font-size:14px;color:var(--ink-700)')}>Next serial for each. It can only go up, so ticket numbers never repeat.</span>
        <div class="admin-grid">
          <label class="admin-row">Next inward<input type="number" value=${A.counters.in} onChange=${e => setA({counters:{...A.counters, in:e.target.value}})} /></label>
          <label class="admin-row">Next outward<input type="number" value=${A.counters.out} onChange=${e => setA({counters:{...A.counters, out:e.target.value}})} /></label>
        </div>
      </div>
    </div>
  </div>
  <div style=${css('display:flex;align-items:center;justify-content:flex-end;gap:10px;margin-top:14px')}>
    ${A.err && h`<span style=${css('margin-right:auto;font-size:15px;color:#C62828;font-weight:700')}>${A.err}</span>`}
    ${A.msg && h`<span style=${css('margin-right:auto;font-size:15px;color:var(--green-700);font-weight:700')}>${A.msg}</span>`}
    <${Button} variant="ghost" onClick=${close}>Close<//>
    <${Button} onClick=${save}>Save settings<//>
  </div>
<//>`;
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(h`<${App} />`);
})();
