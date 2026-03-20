import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { api, setToken, getToken, clearToken } from './api';

/* ═══════════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════════ */
const nid = () => Math.random().toString(36).slice(2, 12);
const fmt = (n) => {
  if (n == null) return '—';
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
  return `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
};
const pct = (v) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`);
const TYPES = ['FD','PPF','EPF','MF','IN_STOCK','IN_ETF','US_STOCK','REAL_ESTATE'];
const TYPE_LABELS = { FD:'Fixed Deposit', PPF:'PPF', EPF:'EPF', MF:'Mutual Fund', IN_STOCK:'Indian Stock', IN_ETF:'Indian ETF', US_STOCK:'US Stock', REAL_ESTATE:'Real Estate' };
const FIXED = ['FD','PPF','EPF','REAL_ESTATE'];

const getVal = (h) => {
  if (FIXED.includes(h.type)) return h.current_value || h.purchase_value || h.principal || 0;
  if (h.current_value) return h.current_value;
  return (h.net_units || 0) * (h.avg_cost || 0);
};
const getInv = (h) => {
  if (FIXED.includes(h.type)) return h.principal || h.purchase_value || 0;
  return (h.net_units || 0) * (h.avg_cost || 0);
};

/* ═══════════════════════════════════════════════════════════════
   STYLES (CSS-in-JS, dark vault theme)
   ═══════════════════════════════════════════════════════════════ */
const G = {
  bg: '#0a0e17', card: '#111827', cardHover: '#1a2332', border: '#1e293b',
  accent: '#c9a55c', accentDim: '#a07d3a', accentGlow: 'rgba(201,165,92,0.15)',
  text: '#e2e8f0', textDim: '#94a3b8', textMuted: '#475569',
  green: '#22c55e', red: '#ef4444', blue: '#3b82f6',
  radius: '10px', font: "'DM Sans', sans-serif", mono: "'JetBrains Mono', monospace",
};
const globalCSS = `
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:${G.bg}; color:${G.text}; font-family:${G.font}; -webkit-font-smoothing:antialiased; }
  ::-webkit-scrollbar { width:6px; } ::-webkit-scrollbar-track { background:${G.bg}; }
  ::-webkit-scrollbar-thumb { background:${G.border}; border-radius:3px; }
  input, select, textarea { background:${G.bg}; color:${G.text}; border:1px solid ${G.border}; border-radius:8px;
    padding:10px 14px; font-family:${G.font}; font-size:14px; outline:none; transition:border .2s; width:100%; }
  input:focus, select:focus, textarea:focus { border-color:${G.accent}; }
  button { font-family:${G.font}; cursor:pointer; transition:all .2s; }
  @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }
  @keyframes slideUp { from{opacity:0;transform:translateY(20px)} to{opacity:1;transform:none} }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
`;

const Btn = ({ children, variant = 'primary', style, ...p }) => (
  <button {...p} style={{
    padding: '10px 20px', borderRadius: '8px', fontWeight: 600, fontSize: '13px',
    border: variant === 'ghost' ? `1px solid ${G.border}` : 'none',
    background: variant === 'primary' ? `linear-gradient(135deg, ${G.accent}, ${G.accentDim})` :
      variant === 'danger' ? G.red : 'transparent',
    color: variant === 'primary' ? '#0a0e17' : variant === 'danger' ? '#fff' : G.textDim,
    letterSpacing: '0.02em', ...style,
  }}>{children}</button>
);

/* ═══════════════════════════════════════════════════════════════
   AUTH SCREEN (Email + Google OAuth with vault passphrase)
   ═══════════════════════════════════════════════════════════════ */
function AuthScreen({ onAuth }) {
  const [mode, setMode] = useState('login'); // login | register | google_setup | google_unlock
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [googleClientId, setGoogleClientId] = useState('');
  // Google flow state
  const [googleInfo, setGoogleInfo] = useState(null); // {email, name, sub}
  const [vaultPassphrase, setVaultPassphrase] = useState('');

  // Check if Google login is configured
  useEffect(() => {
    api.getGoogleClientId().then(r => {
      if (r.enabled && r.client_id) {
        setGoogleEnabled(true);
        setGoogleClientId(r.client_id);
        // Load Google Sign-In script
        const script = document.createElement('script');
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.onload = () => initGoogleButton(r.client_id);
        document.body.appendChild(script);
      }
    }).catch(() => {});
  }, []);

  const initGoogleButton = (clientId) => {
    if (!window.google) return;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: handleGoogleCredential,
    });
    const container = document.getElementById('google-signin-btn');
    if (container) {
      window.google.accounts.id.renderButton(container, {
        theme: 'filled_black', size: 'large', width: 340, text: 'signin_with',
        shape: 'rectangular',
      });
    }
  };

  // Re-render Google button when mode changes
  useEffect(() => {
    if (googleEnabled && googleClientId && window.google && (mode === 'login' || mode === 'register')) {
      setTimeout(() => initGoogleButton(googleClientId), 100);
    }
  }, [mode, googleEnabled]);

  const handleGoogleCredential = async (response) => {
    setError(''); setLoading(true);
    try {
      const res = await api.googleLogin(response.credential);
      setToken(res.access_token);
      localStorage.setItem('wl_user', JSON.stringify(res));
      setGoogleInfo({ email: res.email, name: res.display_name });
      if (!res.vault_exists) {
        setMode('google_setup');
      } else {
        setMode('google_unlock');
      }
    } catch (err) { setError(err.message); }
    setLoading(false);
  };

  const submitEmail = async (e) => {
    e.preventDefault(); setError(''); setLoading(true);
    try {
      const fn = mode === 'login' ? api.login : api.register;
      const payload = mode === 'login' ? { email, password } : { email, password, display_name: name };
      const res = await fn(payload);
      setToken(res.access_token);
      localStorage.setItem('wl_user', JSON.stringify(res));
      onAuth(res);
    } catch (err) { setError(err.message); }
    setLoading(false);
  };

  const submitGoogleSetup = async (e) => {
    e.preventDefault(); setError(''); setLoading(true);
    try {
      const res = await api.vaultSetup(vaultPassphrase);
      setToken(res.access_token);
      localStorage.setItem('wl_user', JSON.stringify(res));
      onAuth(res);
    } catch (err) { setError(err.message); }
    setLoading(false);
  };

  const submitGoogleUnlock = async (e) => {
    e.preventDefault(); setError(''); setLoading(true);
    try {
      const res = await api.vaultUnlock(vaultPassphrase);
      setToken(res.access_token);
      localStorage.setItem('wl_user', JSON.stringify(res));
      onAuth(res);
    } catch (err) { setError(err.message); }
    setLoading(false);
  };

  const divider = (
    <div style={{ display:'flex', alignItems:'center', gap:12, margin:'18px 0' }}>
      <div style={{ flex:1, height:1, background:G.border }} />
      <span style={{ color:G.textMuted, fontSize:11, letterSpacing:'0.05em' }}>OR</span>
      <div style={{ flex:1, height:1, background:G.border }} />
    </div>
  );

  return (
    <div style={{ minHeight:'100vh', display:'flex', alignItems:'center', justifyContent:'center',
      background:`radial-gradient(ellipse at 30% 20%, rgba(201,165,92,0.06) 0%, transparent 60%), ${G.bg}` }}>
      <div style={{ width:420, background:G.card, borderRadius:16, padding:'48px 40px',
        border:`1px solid ${G.border}`, animation:'slideUp .5s ease' }}>
        <div style={{ textAlign:'center', marginBottom:32 }}>
          <div style={{ fontSize:40, marginBottom:8 }}>🔐</div>
          <h1 style={{ fontSize:24, fontWeight:700, letterSpacing:'-0.02em' }}>WealthLens
            <span style={{ color:G.accent, fontSize:13, fontWeight:500, marginLeft:8, verticalAlign:'super' }}>OSS</span>
          </h1>
          <p style={{ color:G.textDim, fontSize:13, marginTop:4 }}>Zero-knowledge family wealth vault</p>
        </div>

        {/* ── Google Vault Setup (new Google user) ── */}
        {mode === 'google_setup' && (
          <div style={{ animation:'fadeIn .3s ease' }}>
            <div style={{ textAlign:'center', marginBottom:20 }}>
              <div style={{ fontSize:14, fontWeight:600, color:G.accent }}>Welcome, {googleInfo?.name}</div>
              <div style={{ fontSize:12, color:G.textDim, marginTop:4 }}>{googleInfo?.email}</div>
              <div style={{ fontSize:12, color:G.textMuted, marginTop:8, lineHeight:1.5 }}>
                Set a <strong style={{ color:G.accent }}>vault PIN</strong> to encrypt your data.<br/>
                This is separate from your Google password.
              </div>
            </div>
            <form onSubmit={submitGoogleSetup} style={{ display:'flex', flexDirection:'column', gap:14 }}>
              <input type="password" placeholder="Vault PIN (min 4 characters)" value={vaultPassphrase}
                onChange={e => setVaultPassphrase(e.target.value)} required minLength={4} autoFocus />
              {error && <div style={{ color:G.red, fontSize:12, padding:'8px 12px', background:'rgba(239,68,68,0.1)', borderRadius:6 }}>{error}</div>}
              <Btn type="submit" style={{ width:'100%', padding:'12px' }} disabled={loading}>
                {loading ? '⏳ Creating vault...' : 'Create Encrypted Vault'}
              </Btn>
              <button type="button" onClick={() => { setMode('login'); setError(''); setGoogleInfo(null); }}
                style={{ background:'none', border:'none', color:G.textMuted, fontSize:12, cursor:'pointer' }}>
                ← Back to sign in
              </button>
            </form>
          </div>
        )}

        {/* ── Google Vault Unlock (existing Google user) ── */}
        {mode === 'google_unlock' && (
          <div style={{ animation:'fadeIn .3s ease' }}>
            <div style={{ textAlign:'center', marginBottom:20 }}>
              <div style={{ fontSize:14, fontWeight:600, color:G.accent }}>Welcome back, {googleInfo?.name}</div>
              <div style={{ fontSize:12, color:G.textDim, marginTop:4 }}>{googleInfo?.email}</div>
              <div style={{ fontSize:12, color:G.textMuted, marginTop:8 }}>Enter your vault PIN to decrypt your data.</div>
            </div>
            <form onSubmit={submitGoogleUnlock} style={{ display:'flex', flexDirection:'column', gap:14 }}>
              <input type="password" placeholder="Vault PIN" value={vaultPassphrase}
                onChange={e => setVaultPassphrase(e.target.value)} required autoFocus />
              {error && <div style={{ color:G.red, fontSize:12, padding:'8px 12px', background:'rgba(239,68,68,0.1)', borderRadius:6 }}>{error}</div>}
              <Btn type="submit" style={{ width:'100%', padding:'12px' }} disabled={loading}>
                {loading ? '⏳ Decrypting vault...' : 'Unlock Vault'}
              </Btn>
              <button type="button" onClick={() => { setMode('login'); setError(''); setGoogleInfo(null); }}
                style={{ background:'none', border:'none', color:G.textMuted, fontSize:12, cursor:'pointer' }}>
                ← Back to sign in
              </button>
            </form>
          </div>
        )}

        {/* ── Email Login / Register ── */}
        {(mode === 'login' || mode === 'register') && (
          <>
            <div style={{ display:'flex', gap:4, background:G.bg, borderRadius:8, padding:3, marginBottom:24 }}>
              {['login','register'].map(m => (
                <button key={m} onClick={() => { setMode(m); setError(''); }}
                  style={{ flex:1, padding:'8px 0', borderRadius:6, border:'none', fontSize:13, fontWeight:600,
                    background: mode === m ? G.card : 'transparent',
                    color: mode === m ? G.accent : G.textMuted }}>
                  {m === 'login' ? 'Sign In' : 'Create Account'}
                </button>
              ))}
            </div>

            {/* Google Sign-In button */}
            {googleEnabled && (
              <>
                <div id="google-signin-btn" style={{ display:'flex', justifyContent:'center' }} />
                {divider}
              </>
            )}

            <form onSubmit={submitEmail} style={{ display:'flex', flexDirection:'column', gap:14 }}>
              {mode === 'register' && <input placeholder="Full Name" value={name} onChange={e => setName(e.target.value)} required />}
              <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} required />
              <input type="password" placeholder={mode === 'register' ? "Password (this encrypts your data)" : "Password"}
                value={password} onChange={e => setPassword(e.target.value)} required minLength={8} />
              {error && <div style={{ color:G.red, fontSize:12, padding:'8px 12px', background:'rgba(239,68,68,0.1)', borderRadius:6 }}>{error}</div>}
              <Btn type="submit" style={{ width:'100%', padding:'12px', marginTop:4 }} disabled={loading}>
                {loading ? '⏳ Securing vault...' : mode === 'login' ? 'Unlock Vault' : 'Create Encrypted Vault'}
              </Btn>
            </form>
            <p style={{ textAlign:'center', color:G.textMuted, fontSize:11, marginTop:20, lineHeight:1.6 }}>
              Your password derives the encryption key.<br/>
              We <strong style={{ color:G.accent }}>cannot</strong> see or recover your data.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   MODAL WRAPPER
   ═══════════════════════════════════════════════════════════════ */
function Modal({ open, onClose, title, children, width = 520 }) {
  if (!open) return null;
  return (
    <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.7)',
      backdropFilter:'blur(4px)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:1000 }}>
      <div onClick={e => e.stopPropagation()} style={{ width, maxWidth:'95vw', maxHeight:'85vh', overflow:'auto',
        background:G.card, borderRadius:14, border:`1px solid ${G.border}`, animation:'slideUp .3s ease' }}>
        <div style={{ padding:'20px 24px', borderBottom:`1px solid ${G.border}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <h3 style={{ fontSize:16, fontWeight:600 }}>{title}</h3>
          <button onClick={onClose} style={{ background:'none', border:'none', color:G.textDim, fontSize:20 }}>✕</button>
        </div>
        <div style={{ padding:24 }}>{children}</div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   DONUT CHART (SVG)
   ═══════════════════════════════════════════════════════════════ */
function DonutChart({ data, size = 200 }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (!total) return null;
  const r = size / 2 - 10, cx = size / 2, cy = size / 2;
  const colors = ['#c9a55c','#3b82f6','#22c55e','#ef4444','#8b5cf6','#ec4899','#f59e0b','#06b6d4'];
  let cum = 0;
  const arcs = data.filter(d => d.value > 0).map((d, i) => {
    const frac = d.value / total;
    const start = cum * 2 * Math.PI - Math.PI / 2;
    cum += frac;
    const end = cum * 2 * Math.PI - Math.PI / 2;
    const large = frac > 0.5 ? 1 : 0;
    const x1 = cx + r * Math.cos(start), y1 = cy + r * Math.sin(start);
    const x2 = cx + r * Math.cos(end), y2 = cy + r * Math.sin(end);
    return { ...d, path: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`, color: colors[i % colors.length], pct: (frac * 100).toFixed(1) };
  });
  return (
    <div style={{ display:'flex', gap:24, alignItems:'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {arcs.map((a, i) => <path key={i} d={a.path} fill={a.color} opacity={0.85} stroke={G.card} strokeWidth={2} />)}
        <circle cx={cx} cy={cy} r={r * 0.55} fill={G.card} />
        <text x={cx} y={cy - 6} textAnchor="middle" fill={G.text} fontSize={16} fontWeight={700} fontFamily={G.mono}>{fmt(total)}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fill={G.textDim} fontSize={10}>Total</text>
      </svg>
      <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
        {arcs.map((a, i) => (
          <div key={i} style={{ display:'flex', alignItems:'center', gap:8, fontSize:12 }}>
            <div style={{ width:10, height:10, borderRadius:3, background:a.color, flexShrink:0 }} />
            <span style={{ color:G.textDim }}>{a.label}</span>
            <span style={{ fontFamily:G.mono, color:G.text }}>{a.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   OVERVIEW TAB
   ═══════════════════════════════════════════════════════════════ */
function OverviewTab({ holdings, members, goals, alerts }) {
  const allCur = holdings.reduce((s, h) => s + getVal(h), 0);
  const allInv = holdings.reduce((s, h) => s + getInv(h), 0);
  const gain = allCur - allInv;
  const ret = allInv > 0 ? (gain / allInv) * 100 : 0;

  const byType = TYPES.map(t => {
    const v = holdings.filter(h => h.type === t).reduce((s, h) => s + getVal(h), 0);
    return { label: TYPE_LABELS[t] || t, value: v };
  }).filter(d => d.value > 0);

  const mSum = members.map(m => {
    const mh = holdings.filter(h => h.member_id === m.id);
    const cur = mh.reduce((s, h) => s + getVal(h), 0);
    const inv = mh.reduce((s, h) => s + getInv(h), 0);
    return { ...m, cur, inv, gain: cur - inv, share: allCur > 0 ? (cur / allCur) * 100 : 0 };
  });

  const trigAlerts = alerts.filter(a => {
    if (!a.active) return false;
    if (a.type === 'RETURN_TARGET') return ret < a.threshold;
    const typeVal = holdings.filter(h => h.type === a.assetType).reduce((s, h) => s + getVal(h), 0);
    const typePct = allCur > 0 ? (typeVal / allCur) * 100 : 0;
    if (a.type === 'ALLOCATION_DRIFT') return typePct > a.threshold;
    if (a.type === 'CONCENTRATION') return typePct < a.threshold;
    return false;
  });

  const kpis = [
    { label: 'Total Portfolio', value: fmt(allCur), sub: `Invested: ${fmt(allInv)}`, color: G.accent },
    { label: 'Total Gain', value: fmt(gain), sub: pct(ret), color: gain >= 0 ? G.green : G.red },
    { label: 'Holdings', value: holdings.length, sub: `${members.length} members`, color: G.blue },
    { label: 'Active Alerts', value: trigAlerts.length, sub: `of ${alerts.length} rules`, color: trigAlerts.length > 0 ? G.red : G.green },
  ];

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:24 }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(200px, 1fr))', gap:16 }}>
        {kpis.map((k, i) => (
          <div key={i} style={{ background:G.card, borderRadius:G.radius, padding:'20px 24px',
            border:`1px solid ${G.border}`, animation:`fadeIn .4s ease ${i * 0.1}s both` }}>
            <div style={{ color:G.textDim, fontSize:11, textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:8 }}>{k.label}</div>
            <div style={{ fontSize:24, fontWeight:700, fontFamily:G.mono, color:k.color }}>{k.value}</div>
            <div style={{ fontSize:12, color:G.textDim, marginTop:4 }}>{k.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20 }}>
        <div style={{ background:G.card, borderRadius:G.radius, padding:24, border:`1px solid ${G.border}` }}>
          <h3 style={{ fontSize:14, fontWeight:600, marginBottom:16, color:G.textDim }}>Asset Allocation</h3>
          <DonutChart data={byType} />
        </div>
        <div style={{ background:G.card, borderRadius:G.radius, padding:24, border:`1px solid ${G.border}` }}>
          <h3 style={{ fontSize:14, fontWeight:600, marginBottom:16, color:G.textDim }}>Member Breakdown</h3>
          {mSum.map((m, i) => (
            <div key={m.id} style={{ marginBottom:14 }}>
              <div style={{ display:'flex', justifyContent:'space-between', fontSize:13, marginBottom:4 }}>
                <span>{m.name} <span style={{ color:G.textMuted, fontSize:11 }}>({m.relation})</span></span>
                <span style={{ fontFamily:G.mono }}>{fmt(m.cur)} <span style={{ color: m.gain >= 0 ? G.green : G.red, fontSize:11 }}>{pct(m.inv > 0 ? (m.gain / m.inv) * 100 : 0)}</span></span>
              </div>
              <div style={{ height:6, background:G.bg, borderRadius:3, overflow:'hidden' }}>
                <div style={{ height:'100%', width:`${m.share}%`, background:`linear-gradient(90deg, ${G.accent}, ${G.accentDim})`, borderRadius:3, transition:'width .5s' }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {trigAlerts.length > 0 && (
        <div style={{ background:'rgba(239,68,68,0.08)', border:`1px solid rgba(239,68,68,0.2)`, borderRadius:G.radius, padding:16 }}>
          <div style={{ fontSize:13, fontWeight:600, color:G.red, marginBottom:8 }}>⚠ {trigAlerts.length} Alert{trigAlerts.length > 1 ? 's' : ''} Triggered</div>
          {trigAlerts.map((a, i) => (
            <div key={i} style={{ fontSize:12, color:G.textDim, padding:'4px 0' }}>• {a.label} — threshold: {a.threshold}%</div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   HOLDINGS TAB
   ═══════════════════════════════════════════════════════════════ */
function HoldingsTab({ holdings, members, onAdd, onDelete, onRefresh, onTxnOpen }) {
  const [selMember, setSelMember] = useState('all');
  const [filterType, setFilterType] = useState('ALL');
  const [refreshing, setRefreshing] = useState(false);

  const visH = holdings.filter(h =>
    (selMember === 'all' || h.member_id === selMember) &&
    (filterType === 'ALL' || h.type === filterType)
  );
  const totCur = visH.reduce((s, h) => s + getVal(h), 0);
  const totInv = visH.reduce((s, h) => s + getInv(h), 0);

  const doRefresh = async () => { setRefreshing(true); await onRefresh(); setRefreshing(false); };

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16, flexWrap:'wrap', gap:12 }}>
        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
          <button onClick={() => setSelMember('all')} style={{ padding:'6px 14px', borderRadius:20, border:`1px solid ${selMember === 'all' ? G.accent : G.border}`,
            background: selMember === 'all' ? G.accentGlow : 'transparent', color: selMember === 'all' ? G.accent : G.textDim, fontSize:12, fontWeight:500 }}>All</button>
          {members.map(m => (
            <button key={m.id} onClick={() => setSelMember(m.id)} style={{ padding:'6px 14px', borderRadius:20,
              border:`1px solid ${selMember === m.id ? G.accent : G.border}`,
              background: selMember === m.id ? G.accentGlow : 'transparent',
              color: selMember === m.id ? G.accent : G.textDim, fontSize:12, fontWeight:500 }}>{m.name}</button>
          ))}
        </div>
        <div style={{ display:'flex', gap:8 }}>
          <select value={filterType} onChange={e => setFilterType(e.target.value)} style={{ width:160, padding:'6px 10px', fontSize:12 }}>
            <option value="ALL">All Types</option>
            {TYPES.map(t => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
          </select>
          <Btn variant="ghost" onClick={doRefresh} style={{ fontSize:12, padding:'6px 14px' }}>
            {refreshing ? '⏳' : '↻'} Refresh
          </Btn>
          <Btn onClick={onAdd} style={{ fontSize:12, padding:'6px 16px' }}>+ Add</Btn>
        </div>
      </div>

      <div style={{ background:G.card, borderRadius:G.radius, border:`1px solid ${G.border}`, overflow:'hidden' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
          <thead>
            <tr style={{ borderBottom:`1px solid ${G.border}` }}>
              {['Name','Type','Current','Invested','Gain','Units','Actions'].map(h => (
                <th key={h} style={{ padding:'12px 16px', textAlign:'left', color:G.textMuted, fontSize:11, fontWeight:600, textTransform:'uppercase', letterSpacing:'0.06em' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visH.map(h => {
              const v = getVal(h), inv = getInv(h), g = v - inv;
              return (
                <tr key={h.id} style={{ borderBottom:`1px solid ${G.border}`, cursor:'pointer' }}
                  onClick={() => onTxnOpen(h)}>
                  <td style={{ padding:'12px 16px', fontWeight:500 }}>{h.name || '—'}</td>
                  <td style={{ padding:'12px 16px' }}><span style={{ padding:'3px 8px', borderRadius:4, background:G.bg, fontSize:11, color:G.textDim }}>{TYPE_LABELS[h.type] || h.type}</span></td>
                  <td style={{ padding:'12px 16px', fontFamily:G.mono }}>{fmt(v)}</td>
                  <td style={{ padding:'12px 16px', fontFamily:G.mono, color:G.textDim }}>{fmt(inv)}</td>
                  <td style={{ padding:'12px 16px', fontFamily:G.mono, color: g >= 0 ? G.green : G.red }}>{fmt(g)}</td>
                  <td style={{ padding:'12px 16px', fontFamily:G.mono, color:G.textDim }}>{h.net_units ? h.net_units.toFixed(3) : '—'}</td>
                  <td style={{ padding:'12px 16px' }}>
                    <button onClick={e => { e.stopPropagation(); onDelete(h.id); }}
                      style={{ background:'none', border:'none', color:G.red, fontSize:14, cursor:'pointer', opacity:0.6 }}>✕</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr style={{ background:G.bg }}>
              <td colSpan={2} style={{ padding:'12px 16px', fontWeight:600, fontSize:12 }}>Total ({visH.length} holdings)</td>
              <td style={{ padding:'12px 16px', fontFamily:G.mono, fontWeight:700, color:G.accent }}>{fmt(totCur)}</td>
              <td style={{ padding:'12px 16px', fontFamily:G.mono }}>{fmt(totInv)}</td>
              <td style={{ padding:'12px 16px', fontFamily:G.mono, color: totCur - totInv >= 0 ? G.green : G.red }}>{fmt(totCur - totInv)}</td>
              <td colSpan={2} />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   GOALS TAB
   ═══════════════════════════════════════════════════════════════ */
function GoalsTab({ goals, holdings, members, onSave }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name:'', targetAmount:'', targetDate:'', category:'', priority:1, linkedMembers:['all'], monthlyContrib:'', notes:'' });

  const allCur = holdings.reduce((s, h) => s + getVal(h), 0);
  const goalCur = (g) => {
    if (g.linkedMembers.includes('all')) return allCur;
    return holdings.filter(h => g.linkedMembers.includes(h.member_id)).reduce((s, h) => s + getVal(h), 0);
  };

  const addGoal = () => {
    const g = { id: nid(), ...form, targetAmount: +form.targetAmount, monthlyContrib: +form.monthlyContrib || 0, color: `#${Math.floor(Math.random()*16777215).toString(16)}` };
    onSave([...goals, g]);
    setShowAdd(false);
    setForm({ name:'', targetAmount:'', targetDate:'', category:'', priority:1, linkedMembers:['all'], monthlyContrib:'', notes:'' });
  };

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:16 }}>
        <h3 style={{ fontSize:16, fontWeight:600 }}>Financial Goals</h3>
        <Btn onClick={() => setShowAdd(true)} style={{ fontSize:12, padding:'6px 16px' }}>+ Add Goal</Btn>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(320px, 1fr))', gap:16 }}>
        {[...goals].sort((a, b) => (a.priority || 99) - (b.priority || 99)).map(g => {
          const cur = goalCur(g);
          const prog = Math.min((cur / (g.targetAmount || 1)) * 100, 100);
          const rem = Math.max(0, g.targetAmount - cur);
          return (
            <div key={g.id} style={{ background:G.card, borderRadius:G.radius, padding:20, border:`1px solid ${G.border}`, borderLeft:`3px solid ${g.color || G.accent}` }}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:8 }}>
                <span style={{ fontWeight:600, fontSize:14 }}>{g.name}</span>
                <span style={{ fontSize:11, color:G.textMuted }}>P{g.priority}</span>
              </div>
              <div style={{ height:8, background:G.bg, borderRadius:4, overflow:'hidden', marginBottom:10 }}>
                <div style={{ height:'100%', width:`${prog}%`, background:`linear-gradient(90deg, ${g.color || G.accent}, ${G.accentDim})`, borderRadius:4 }} />
              </div>
              <div style={{ display:'flex', justifyContent:'space-between', fontSize:12, color:G.textDim }}>
                <span>{fmt(cur)} / {fmt(g.targetAmount)}</span>
                <span>{prog.toFixed(0)}%</span>
              </div>
              <div style={{ fontSize:11, color:G.textMuted, marginTop:6 }}>Remaining: {fmt(rem)} • Target: {g.targetDate}</div>
              <button onClick={() => onSave(goals.filter(x => x.id !== g.id))}
                style={{ marginTop:10, background:'none', border:'none', color:G.red, fontSize:11, cursor:'pointer', opacity:0.6 }}>Remove</button>
            </div>
          );
        })}
      </div>
      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add Goal">
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <input placeholder="Goal name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          <input type="number" placeholder="Target amount (₹)" value={form.targetAmount} onChange={e => setForm({ ...form, targetAmount: e.target.value })} />
          <input type="date" value={form.targetDate} onChange={e => setForm({ ...form, targetDate: e.target.value })} />
          <input placeholder="Category" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} />
          <Btn onClick={addGoal}>Add Goal</Btn>
        </div>
      </Modal>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   MEMBERS TAB
   ═══════════════════════════════════════════════════════════════ */
function MembersTab({ members, holdings, onSave }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: '', relation: 'Self' });
  const allCur = holdings.reduce((s, h) => s + getVal(h), 0);

  const addMember = () => {
    onSave([...members, { id: nid(), ...form }]);
    setShowAdd(false);
    setForm({ name: '', relation: 'Self' });
  };

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:16 }}>
        <h3 style={{ fontSize:16, fontWeight:600 }}>Family Members</h3>
        <Btn onClick={() => setShowAdd(true)} style={{ fontSize:12, padding:'6px 16px' }}>+ Add Member</Btn>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(280px, 1fr))', gap:16 }}>
        {members.map(m => {
          const mh = holdings.filter(h => h.member_id === m.id);
          const cur = mh.reduce((s, h) => s + getVal(h), 0);
          const inv = mh.reduce((s, h) => s + getInv(h), 0);
          const share = allCur > 0 ? (cur / allCur) * 100 : 0;
          const byT = TYPES.map(t => ({ label: TYPE_LABELS[t], value: mh.filter(h => h.type === t).reduce((s, h) => s + getVal(h), 0) })).filter(d => d.value > 0);
          return (
            <div key={m.id} style={{ background:G.card, borderRadius:G.radius, padding:20, border:`1px solid ${G.border}` }}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:12 }}>
                <div>
                  <div style={{ fontWeight:600, fontSize:15 }}>{m.name}</div>
                  <div style={{ fontSize:11, color:G.textMuted }}>{m.relation}</div>
                </div>
                <div style={{ textAlign:'right' }}>
                  <div style={{ fontFamily:G.mono, fontWeight:600, color:G.accent }}>{fmt(cur)}</div>
                  <div style={{ fontSize:11, color:G.textDim }}>{share.toFixed(1)}% of total</div>
                </div>
              </div>
              <div style={{ height:6, background:G.bg, borderRadius:3, overflow:'hidden', marginBottom:12 }}>
                <div style={{ height:'100%', width:`${share}%`, background:`linear-gradient(90deg, ${G.accent}, ${G.accentDim})`, borderRadius:3 }} />
              </div>
              {byT.map((d, i) => (
                <div key={i} style={{ display:'flex', justifyContent:'space-between', fontSize:11, color:G.textDim, padding:'2px 0' }}>
                  <span>{d.label}</span><span style={{ fontFamily:G.mono }}>{fmt(d.value)}</span>
                </div>
              ))}
              <button onClick={() => onSave(members.filter(x => x.id !== m.id))}
                style={{ marginTop:12, background:'none', border:'none', color:G.red, fontSize:11, cursor:'pointer', opacity:0.5 }}>Remove</button>
            </div>
          );
        })}
      </div>
      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add Family Member">
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <input placeholder="Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          <select value={form.relation} onChange={e => setForm({ ...form, relation: e.target.value })}>
            {['Self','Spouse','Son','Daughter','Father','Mother','Other'].map(r => <option key={r}>{r}</option>)}
          </select>
          <Btn onClick={addMember}>Add Member</Btn>
        </div>
      </Modal>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   ALERTS TAB
   ═══════════════════════════════════════════════════════════════ */
function AlertsTab({ alerts, holdings, onSave }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ type:'ALLOCATION_DRIFT', assetType:'MF', threshold:'', label:'' });
  const allCur = holdings.reduce((s, h) => s + getVal(h), 0);

  const addAlert = () => {
    onSave([...alerts, { id: nid(), ...form, threshold: +form.threshold, active: true }]);
    setShowAdd(false);
    setForm({ type:'ALLOCATION_DRIFT', assetType:'MF', threshold:'', label:'' });
  };

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:16 }}>
        <h3 style={{ fontSize:16, fontWeight:600 }}>Alert Rules</h3>
        <Btn onClick={() => setShowAdd(true)} style={{ fontSize:12, padding:'6px 16px' }}>+ Add Alert</Btn>
      </div>
      <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
        {alerts.map(a => {
          const typeVal = holdings.filter(h => h.type === a.assetType).reduce((s, h) => s + getVal(h), 0);
          const typePct = allCur > 0 ? (typeVal / allCur) * 100 : 0;
          const totalRet = allCur > 0 ? ((allCur - holdings.reduce((s, h) => s + getInv(h), 0)) / holdings.reduce((s, h) => s + getInv(h), 0)) * 100 : 0;
          const triggered = a.type === 'ALLOCATION_DRIFT' ? typePct > a.threshold :
            a.type === 'CONCENTRATION' ? typePct < a.threshold : totalRet < a.threshold;
          return (
            <div key={a.id} style={{ background:G.card, borderRadius:G.radius, padding:16, border:`1px solid ${triggered ? 'rgba(239,68,68,0.3)' : G.border}`,
              display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <div>
                <div style={{ fontWeight:500, fontSize:13 }}>{triggered ? '🔴' : '🟢'} {a.label}</div>
                <div style={{ fontSize:11, color:G.textDim }}>{a.type} • {a.assetType || 'Portfolio'} • Threshold: {a.threshold}%</div>
              </div>
              <div style={{ display:'flex', gap:8 }}>
                <button onClick={() => onSave(alerts.map(x => x.id === a.id ? { ...x, active: !x.active } : x))}
                  style={{ background:'none', border:`1px solid ${G.border}`, borderRadius:6, padding:'4px 10px', color:G.textDim, fontSize:11, cursor:'pointer' }}>
                  {a.active ? 'Disable' : 'Enable'}
                </button>
                <button onClick={() => onSave(alerts.filter(x => x.id !== a.id))}
                  style={{ background:'none', border:'none', color:G.red, fontSize:14, cursor:'pointer' }}>✕</button>
              </div>
            </div>
          );
        })}
      </div>
      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add Alert Rule">
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <input placeholder="Label" value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} />
          <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}>
            <option value="ALLOCATION_DRIFT">Allocation Drift (over-weight)</option>
            <option value="CONCENTRATION">Concentration (under-weight)</option>
            <option value="RETURN_TARGET">Return Target</option>
          </select>
          {form.type !== 'RETURN_TARGET' && (
            <select value={form.assetType} onChange={e => setForm({ ...form, assetType: e.target.value })}>
              {TYPES.map(t => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
            </select>
          )}
          <input type="number" placeholder="Threshold %" value={form.threshold} onChange={e => setForm({ ...form, threshold: e.target.value })} />
          <Btn onClick={addAlert}>Add Alert</Btn>
        </div>
      </Modal>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   AI ADVISOR TAB
   ═══════════════════════════════════════════════════════════════ */
function AdvisorTab({ holdings, members, goals, alerts }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const suggestions = [
    "How is my portfolio allocated? Any rebalancing needed?",
    "Which holdings should I consider selling for tax harvesting?",
    "Am I on track for my financial goals?",
    "Suggest 3 mutual funds to diversify my portfolio",
  ];

  const buildContext = () => {
    const allCur = holdings.reduce((s, h) => s + getVal(h), 0);
    const lines = [`Total portfolio: ${fmt(allCur)} across ${holdings.length} holdings.`];
    members.forEach(m => {
      const mh = holdings.filter(h => h.member_id === m.id);
      const c = mh.reduce((s, h) => s + getVal(h), 0);
      lines.push(`${m.name} (${m.relation}): ${fmt(c)}`);
    });
    lines.push('\nHoldings:');
    holdings.forEach(h => lines.push(`  ${h.name} [${h.type}] cur=${fmt(getVal(h))} inv=${fmt(getInv(h))}`));
    if (goals.length) { lines.push('\nGoals:'); goals.forEach(g => lines.push(`  ${g.name}: target=${fmt(g.targetAmount)} by ${g.targetDate}`)); }
    if (alerts.length) { lines.push('\nAlerts:'); alerts.forEach(a => lines.push(`  ${a.label}: ${a.type} ${a.threshold}%`)); }
    return lines.join('\n');
  };

  const send = async (text) => {
    const userMsg = { role: 'user', content: text || input };
    const newMsgs = [...messages, userMsg];
    setMessages(newMsgs);
    setInput('');
    setLoading(true);
    try {
      const res = await api.aiChat({ messages: newMsgs, context: buildContext() });
      setMessages([...newMsgs, { role: 'assistant', content: res.content }]);
    } catch (e) {
      setMessages([...newMsgs, { role: 'assistant', content: `Error: ${e.message}` }]);
    }
    setLoading(false);
  };

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'calc(100vh - 200px)' }}>
      <div style={{ flex:1, overflow:'auto', display:'flex', flexDirection:'column', gap:12, padding:'8px 0' }}>
        {messages.length === 0 && (
          <div style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:16, color:G.textDim }}>
            <div style={{ fontSize:40 }}>✶</div>
            <div style={{ fontSize:15, fontWeight:500 }}>AI Wealth Advisor</div>
            <div style={{ fontSize:12, color:G.textMuted }}>Ask about your portfolio, goals, tax strategy, or rebalancing</div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:8, maxWidth:500, justifyContent:'center', marginTop:8 }}>
              {suggestions.map((s, i) => (
                <button key={i} onClick={() => send(s)}
                  style={{ padding:'8px 14px', borderRadius:20, border:`1px solid ${G.border}`, background:'transparent', color:G.textDim, fontSize:12, cursor:'pointer' }}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ display:'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{ maxWidth:'75%', padding:'12px 16px', borderRadius:12, fontSize:13, lineHeight:1.6, whiteSpace:'pre-wrap',
              background: m.role === 'user' ? G.accentGlow : G.card,
              border: `1px solid ${m.role === 'user' ? 'rgba(201,165,92,0.2)' : G.border}`,
              color: m.role === 'user' ? G.accent : G.text }}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && <div style={{ color:G.textMuted, fontSize:12, animation:'pulse 1.5s infinite' }}>✶ Analyzing your portfolio...</div>}
      </div>
      <div style={{ display:'flex', gap:8, padding:'12px 0', borderTop:`1px solid ${G.border}` }}>
        <input value={input} onChange={e => setInput(e.target.value)} placeholder="Ask about your portfolio..."
          onKeyDown={e => e.key === 'Enter' && input.trim() && send()}
          style={{ flex:1 }} />
        <Btn onClick={() => input.trim() && send()} disabled={loading || !input.trim()}>Send</Btn>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   TRANSACTION PANEL (modal)
   ═══════════════════════════════════════════════════════════════ */
function TransactionPanel({ holding, onClose, onReload }) {
  const [form, setForm] = useState({ txn_type:'BUY', units:'', price:'', txn_date:'', notes:'' });
  const [loading, setLoading] = useState(false);
  const [manualNav, setManualNav] = useState({ nav:'', date:'', notes:'' });
  const [showManualNav, setShowManualNav] = useState(false);
  const [navLoading, setNavLoading] = useState(false);

  const isMF = holding?.type === 'MF';

  const submit = async () => {
    setLoading(true);
    try {
      await api.addTransaction({
        holding_id: holding.id, txn_type: form.txn_type,
        units: +form.units, price: +form.price,
        txn_date: form.txn_date, notes: form.notes,
      });
      await onReload();
      setForm({ txn_type:'BUY', units:'', price:'', txn_date:'', notes:'' });
    } catch (e) { alert(e.message); }
    setLoading(false);
  };

  const deleteTxn = async (tid) => {
    try { await api.deleteTransaction(tid); await onReload(); } catch (e) { alert(e.message); }
  };

  const submitManualNav = async () => {
    setNavLoading(true);
    try {
      await api.manualNav({
        holding_id: holding.id, nav: +manualNav.nav,
        nav_date: manualNav.date, notes: manualNav.notes || 'Manual NAV entry',
      });
      await onReload();
      setManualNav({ nav:'', date:'', notes:'' });
      setShowManualNav(false);
    } catch (e) { alert(e.message); }
    setNavLoading(false);
  };

  // Try to fetch NAV from MFAPI/AMFI when scheme_code exists
  const fetchCurrentNav = async () => {
    if (!holding?.scheme_code) return;
    setNavLoading(true);
    try {
      const res = await api.mfNav(holding.scheme_code);
      setManualNav({ nav: String(res.nav), date: res.date, notes: `Auto: ${res.source}` });
    } catch (e) {
      // MFAPI + AMFI both failed — leave manual entry empty
      setManualNav(prev => ({ ...prev, notes: 'MFAPI/AMFI unavailable — enter manually' }));
    }
    setNavLoading(false);
  };

  return (
    <Modal open={!!holding} onClose={onClose} title={`Transactions — ${holding?.name}`} width={640}>
      {/* Manual NAV section for MF holdings */}
      {isMF && (
        <div style={{ marginBottom:16, padding:12, background:G.bg, borderRadius:8, border:`1px solid ${G.border}` }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom: showManualNav ? 12 : 0 }}>
            <div style={{ fontSize:12, color:G.textDim }}>
              NAV source: <span style={{ color:G.accent, fontFamily:G.mono }}>{holding?.nav_source || holding?.manual_nav ? 'manual' : 'auto'}</span>
              {holding?.manual_nav && <span style={{ marginLeft:8, fontFamily:G.mono }}>₹{holding.manual_nav}</span>}
            </div>
            <div style={{ display:'flex', gap:6 }}>
              <button onClick={fetchCurrentNav} disabled={navLoading}
                style={{ padding:'4px 10px', borderRadius:6, border:`1px solid ${G.border}`, background:'transparent',
                  color:G.textDim, fontSize:11, cursor:'pointer' }}>
                {navLoading ? '...' : '↻ Fetch NAV'}
              </button>
              <button onClick={() => setShowManualNav(!showManualNav)}
                style={{ padding:'4px 10px', borderRadius:6, border:`1px solid ${G.accent}`, background:G.accentGlow,
                  color:G.accent, fontSize:11, cursor:'pointer' }}>
                {showManualNav ? 'Cancel' : '✎ Manual NAV'}
              </button>
            </div>
          </div>
          {showManualNav && (
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 2fr', gap:8, marginTop:8 }}>
              <input type="number" placeholder="NAV ₹" value={manualNav.nav} step="0.01"
                onChange={e => setManualNav({ ...manualNav, nav: e.target.value })} style={{ fontSize:12, padding:'8px 10px' }} />
              <input type="text" placeholder="Date (DD-MM-YYYY)" value={manualNav.date}
                onChange={e => setManualNav({ ...manualNav, date: e.target.value })} style={{ fontSize:12, padding:'8px 10px' }} />
              <div style={{ display:'flex', gap:6 }}>
                <input placeholder="Notes" value={manualNav.notes}
                  onChange={e => setManualNav({ ...manualNav, notes: e.target.value })} style={{ fontSize:12, padding:'8px 10px', flex:1 }} />
                <Btn onClick={submitManualNav} disabled={!manualNav.nav || navLoading}
                  style={{ fontSize:11, padding:'8px 12px', whiteSpace:'nowrap' }}>
                  {navLoading ? '...' : 'Update'}
                </Btn>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Transaction form */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:16 }}>
        <select value={form.txn_type} onChange={e => setForm({ ...form, txn_type: e.target.value })}>
          <option value="BUY">BUY</option><option value="SELL">SELL</option>
        </select>
        <input type="date" value={form.txn_date} onChange={e => setForm({ ...form, txn_date: e.target.value })} />
        <input type="number" placeholder="Units" value={form.units} onChange={e => setForm({ ...form, units: e.target.value })} />
        <input type="number" placeholder="Price per unit (₹)" value={form.price} onChange={e => setForm({ ...form, price: e.target.value })} />
        <input placeholder="Notes" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} style={{ gridColumn:'span 2' }} />
      </div>
      <Btn onClick={submit} disabled={loading} style={{ width:'100%', marginBottom:20 }}>
        {loading ? 'Adding...' : `Add ${form.txn_type}`}
      </Btn>
      <div style={{ fontSize:12, color:G.textDim, marginBottom:8 }}>History ({(holding?.transactions || []).length} transactions)</div>
      <div style={{ maxHeight:300, overflow:'auto' }}>
        {(holding?.transactions || []).map(t => (
          <div key={t.id} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'8px 0', borderBottom:`1px solid ${G.border}`, fontSize:12 }}>
            <span style={{ color: t.txn_type === 'BUY' ? G.green : G.red, fontWeight:600, width:40 }}>{t.txn_type}</span>
            <span style={{ fontFamily:G.mono }}>{t.units} × {fmt(t.price)}</span>
            <span style={{ color:G.textMuted }}>{t.txn_date}</span>
            <button onClick={() => deleteTxn(t.id)} style={{ background:'none', border:'none', color:G.red, cursor:'pointer', fontSize:13 }}>✕</button>
          </div>
        ))}
      </div>
    </Modal>
  );
}

/* ═══════════════════════════════════════════════════════════════
   ADD HOLDING MODAL
   ═══════════════════════════════════════════════════════════════ */
function AddHoldingModal({ open, onClose, members, onAdd }) {
  const [form, setForm] = useState({ name:'', type:'MF', member_id:'', ticker:'', scheme_code:'',
    purchase_value:'', current_value:'', principal:'', interest_rate:'', start_date:'', maturity_date:'' });
  const [mfResults, setMfResults] = useState([]);
  const [mfQuery, setMfQuery] = useState('');
  const [mfSearching, setMfSearching] = useState(false);
  const [mfSource, setMfSource] = useState('auto'); // auto | amfi

  useEffect(() => {
    if (members.length && !form.member_id) setForm(f => ({ ...f, member_id: members[0].id }));
  }, [members]);

  const searchMF = async () => {
    if (!mfQuery.trim()) return;
    setMfSearching(true);
    try {
      const fn = mfSource === 'amfi' ? api.mfAmfiSearch : api.mfSearch;
      const results = await fn(mfQuery);
      setMfResults(results);
      if (results.length === 0 && mfSource !== 'amfi') {
        // Auto-retry with AMFI
        const amfiResults = await api.mfAmfiSearch(mfQuery);
        setMfResults(amfiResults);
        if (amfiResults.length > 0) setMfSource('amfi');
      }
    } catch (e) { console.error(e); }
    setMfSearching(false);
  };

  const selectMF = (r) => {
    setForm({ ...form, name: r.schemeName, scheme_code: r.schemeCode });
    setMfResults([]);
  };

  const submit = async () => {
    try {
      const payload = { ...form };
      ['purchase_value','current_value','principal','interest_rate'].forEach(k => {
        if (payload[k]) payload[k] = +payload[k]; else delete payload[k];
      });
      await onAdd(payload);
      setForm({ name:'', type:'MF', member_id: members[0]?.id || '', ticker:'', scheme_code:'',
        purchase_value:'', current_value:'', principal:'', interest_rate:'', start_date:'', maturity_date:'' });
      setMfResults([]); setMfQuery('');
      onClose();
    } catch (e) { alert(e.message); }
  };

  const isFixed = FIXED.includes(form.type);

  return (
    <Modal open={open} onClose={onClose} title="Add Holding" width={580}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
          <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}>
            {TYPES.map(t => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
          </select>
          <select value={form.member_id} onChange={e => setForm({ ...form, member_id: e.target.value })}>
            {members.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </div>

        {/* MF Search with AMFI fallback */}
        {form.type === 'MF' && (
          <div style={{ background:G.bg, borderRadius:8, padding:12, border:`1px solid ${G.border}` }}>
            <div style={{ display:'flex', gap:8, marginBottom:8 }}>
              <input placeholder="Search mutual fund by name..." value={mfQuery}
                onChange={e => setMfQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && searchMF()}
                style={{ flex:1, fontSize:12, padding:'8px 10px' }} />
              <button onClick={searchMF} disabled={mfSearching}
                style={{ padding:'6px 12px', borderRadius:6, border:`1px solid ${G.accent}`, background:G.accentGlow,
                  color:G.accent, fontSize:11, fontWeight:600, cursor:'pointer', whiteSpace:'nowrap' }}>
                {mfSearching ? '...' : 'Search'}
              </button>
            </div>
            {mfResults.length > 0 && (
              <div style={{ maxHeight:150, overflow:'auto', borderRadius:6 }}>
                {mfResults.map((r, i) => (
                  <div key={i} onClick={() => selectMF(r)}
                    style={{ padding:'8px 10px', fontSize:11, cursor:'pointer', borderBottom:`1px solid ${G.border}`,
                      color:G.textDim, display:'flex', justifyContent:'space-between', alignItems:'center' }}
                    onMouseEnter={e => e.target.style.background = G.cardHover}
                    onMouseLeave={e => e.target.style.background = 'transparent'}>
                    <span style={{ flex:1 }}>{r.schemeName}</span>
                    <span style={{ fontFamily:G.mono, color:G.textMuted, fontSize:10, marginLeft:8 }}>{r.schemeCode}</span>
                    {r.source === 'amfi' && <span style={{ marginLeft:6, fontSize:9, color:G.accent, background:G.accentGlow, padding:'1px 5px', borderRadius:4 }}>AMFI</span>}
                  </div>
                ))}
              </div>
            )}
            {mfResults.length === 0 && mfQuery && !mfSearching && (
              <div style={{ fontSize:11, color:G.textMuted, padding:'4px 0' }}>
                No results. Try a different name or enter the scheme code manually below.
              </div>
            )}
            <div style={{ display:'flex', gap:6, marginTop:6 }}>
              <button onClick={() => { setMfSource('auto'); setMfResults([]); }}
                style={{ padding:'3px 8px', borderRadius:4, border:'none', fontSize:10, cursor:'pointer',
                  background: mfSource === 'auto' ? G.accentGlow : 'transparent', color: mfSource === 'auto' ? G.accent : G.textMuted }}>
                MFAPI + AMFI
              </button>
              <button onClick={() => { setMfSource('amfi'); setMfResults([]); }}
                style={{ padding:'3px 8px', borderRadius:4, border:'none', fontSize:10, cursor:'pointer',
                  background: mfSource === 'amfi' ? G.accentGlow : 'transparent', color: mfSource === 'amfi' ? G.accent : G.textMuted }}>
                AMFI only
              </button>
            </div>
          </div>
        )}

        <input placeholder="Instrument Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
        {!isFixed && form.type !== 'MF' && <input placeholder="Ticker (e.g. RELIANCE, AAPL)" value={form.ticker} onChange={e => setForm({ ...form, ticker: e.target.value })} />}
        {form.type === 'MF' && <input placeholder="AMFI Scheme Code" value={form.scheme_code} onChange={e => setForm({ ...form, scheme_code: e.target.value })} />}
        {isFixed && (
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            <input type="number" placeholder="Principal (₹)" value={form.principal} onChange={e => setForm({ ...form, principal: e.target.value })} />
            <input type="number" placeholder="Interest Rate %" value={form.interest_rate} onChange={e => setForm({ ...form, interest_rate: e.target.value })} />
            <input type="date" placeholder="Start Date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} />
            <input type="date" placeholder="Maturity Date" value={form.maturity_date} onChange={e => setForm({ ...form, maturity_date: e.target.value })} />
          </div>
        )}
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
          <input type="number" placeholder="Purchase Value (₹)" value={form.purchase_value} onChange={e => setForm({ ...form, purchase_value: e.target.value })} />
          <input type="number" placeholder="Current Value (₹)" value={form.current_value} onChange={e => setForm({ ...form, current_value: e.target.value })} />
        </div>
        <Btn onClick={submit} style={{ width:'100%' }}>Add Holding</Btn>
      </div>
    </Modal>
  );
}

/* ═══════════════════════════════════════════════════════════════
   BUDGET TAB (import, categories, charts, transactions)
   ═══════════════════════════════════════════════════════════════ */
function BudgetTab() {
  const [view, setView] = useState('summary'); // summary | transactions | imports | categories
  const [month, setMonth] = useState(() => { const d=new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`; });
  const [summary, setSummary] = useState(null);
  const [txns, setTxns] = useState([]);
  const [categories, setCategories] = useState([]);
  const [imports, setImports] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importSource, setImportSource] = useState('auto');
  const [importName, setImportName] = useState('');

  const loadData = async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([api.budgetSummary(month), api.budgetCategories()]);
      setSummary(s); setCategories(c);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const loadTxns = async () => {
    try { const t = await api.budgetTransactions(month); setTxns(t); } catch(e) { console.error(e); }
  };

  const loadImports = async () => {
    try { const i = await api.budgetImports(); setImports(i); } catch(e) { console.error(e); }
  };

  useEffect(() => { loadData(); }, [month]);
  useEffect(() => { if(view==='transactions') loadTxns(); if(view==='imports') loadImports(); }, [view, month]);

  const doImport = async () => {
    if (!importFile) return;
    setLoading(true);
    try {
      const res = await api.budgetImport(importFile, importSource, importName);
      alert(`Imported ${res.transactions_imported} transactions from ${res.source}`);
      setShowImport(false); setImportFile(null);
      loadData(); if(view==='imports') loadImports();
    } catch(e) { alert(e.message); }
    setLoading(false);
  };

  const catMap = Object.fromEntries(categories.map(c => [c.id, c]));

  // Pie chart data
  const pieData = (summary?.categories || []).filter(c => !c.is_income && c.total > 0);
  const pieTotal = pieData.reduce((s,d) => s + d.total, 0);

  // Bar chart: budget vs actual
  const barData = (summary?.categories || []).filter(c => !c.is_income && (c.total > 0 || c.budget > 0));

  const kpis = summary ? [
    { label: 'Spending', value: fmt(summary.total_spending), color: G.red },
    { label: 'Income', value: fmt(summary.total_income), color: G.green },
    { label: 'Net', value: fmt(summary.net), color: summary.net >= 0 ? G.green : G.red },
    { label: 'vs Last Month', value: summary.vs_prev_month_pct != null ? pct(summary.vs_prev_month_pct) : '—', color: (summary.vs_prev_month_pct||0) <= 0 ? G.green : G.red },
  ] : [];

  return (
    <div>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16, flexWrap:'wrap', gap:10 }}>
        <div style={{ display:'flex', gap:5 }}>
          {['summary','transactions','imports','categories'].map(v => (
            <button key={v} onClick={() => setView(v)} style={{ padding:'6px 14px', borderRadius:18,
              border:`1px solid ${view===v ? G.accent : G.border}`, background: view===v ? G.accentGlow : 'transparent',
              color: view===v ? G.accent : G.textDim, fontSize:12, fontWeight:500, cursor:'pointer', textTransform:'capitalize' }}>{v}</button>
          ))}
        </div>
        <div style={{ display:'flex', gap:8, alignItems:'center' }}>
          <input type="month" value={month} onChange={e => setMonth(e.target.value)}
            style={{ width:160, padding:'6px 10px', fontSize:12 }} />
          <Btn onClick={() => setShowImport(true)} style={{ fontSize:12, padding:'6px 16px' }}>↑ Import Statement</Btn>
        </div>
      </div>

      {/* Import Modal */}
      <Modal open={showImport} onClose={() => setShowImport(false)} title="Import Bank Statement" width={500}>
        <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
          <div style={{ padding:16, background:G.bg, borderRadius:8, border:`1px dashed ${G.border}`, textAlign:'center' }}>
            <input type="file" accept=".csv,.txt" onChange={e => setImportFile(e.target.files?.[0])}
              style={{ width:'100%' }} />
            <p style={{ color:G.textMuted, fontSize:11, marginTop:8 }}>CSV from: HDFC, SBI, ICICI, Axis, Kotak, or any bank</p>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
            <div>
              <label style={{ fontSize:11, color:G.textDim, display:'block', marginBottom:4 }}>Format detection</label>
              <select value={importSource} onChange={e => setImportSource(e.target.value)} style={{ fontSize:12 }}>
                <option value="auto">Auto-detect</option>
                <option value="hdfc_csv">HDFC Bank</option>
                <option value="sbi_csv">SBI</option>
                <option value="icici_csv">ICICI Bank</option>
                <option value="axis_csv">Axis Bank</option>
                <option value="kotak_csv">Kotak Mahindra</option>
                <option value="generic_csv">Generic CSV</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize:11, color:G.textDim, display:'block', marginBottom:4 }}>Source label</label>
              <input placeholder="e.g. HDFC Savings" value={importName} onChange={e => setImportName(e.target.value)} style={{ fontSize:12 }} />
            </div>
          </div>
          <Btn onClick={doImport} disabled={!importFile || loading} style={{ width:'100%' }}>
            {loading ? 'Parsing & encrypting...' : 'Import & Categorize'}
          </Btn>
          <p style={{ textAlign:'center', color:G.textMuted, fontSize:10, lineHeight:1.5 }}>
            Transactions are encrypted before storage. The operator cannot see your spending data.
            <br/>Import history is retained for 1 year, then auto-deleted.
          </p>
        </div>
      </Modal>

      {/* SUMMARY VIEW */}
      {view === 'summary' && summary && (
        <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
          {/* KPIs */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14 }}>
            {kpis.map((k,i) => (
              <div key={i} style={{ background:G.card, borderRadius:G.radius, padding:'16px 18px', border:`1px solid ${G.border}` }}>
                <div style={{ color:G.textDim, fontSize:10, textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:5 }}>{k.label}</div>
                <div style={{ fontSize:20, fontWeight:700, fontFamily:G.mono, color:k.color }}>{k.value}</div>
              </div>
            ))}
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:18 }}>
            {/* Pie Chart */}
            <div style={{ background:G.card, borderRadius:G.radius, padding:22, border:`1px solid ${G.border}` }}>
              <h3 style={{ fontSize:13, fontWeight:600, marginBottom:14, color:G.textDim, margin:'0 0 14px' }}>Spending by category</h3>
              {pieData.length > 0 ? <DonutChart data={pieData.map(c => ({ label: c.name, value: c.total }))} /> : <div style={{ color:G.textMuted, fontSize:12 }}>No spending data</div>}
            </div>

            {/* Bar Chart: Budget vs Actual */}
            <div style={{ background:G.card, borderRadius:G.radius, padding:22, border:`1px solid ${G.border}` }}>
              <h3 style={{ fontSize:13, fontWeight:600, marginBottom:14, color:G.textDim, margin:'0 0 14px' }}>Budget vs actual</h3>
              <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                {barData.slice(0, 8).map((c, i) => {
                  const maxVal = Math.max(c.total, c.budget || c.total) || 1;
                  const actualPct = Math.min((c.total / maxVal) * 100, 100);
                  const budgetPct = c.budget > 0 ? Math.min((c.budget / maxVal) * 100, 100) : 0;
                  const over = c.budget > 0 && c.total > c.budget;
                  return (
                    <div key={i}>
                      <div style={{ display:'flex', justifyContent:'space-between', fontSize:11, marginBottom:3 }}>
                        <span style={{ color:G.textDim }}>{c.icon} {c.name}</span>
                        <span style={{ fontFamily:G.mono, color: over ? G.red : G.text }}>{fmt(c.total)}{c.budget > 0 ? ` / ${fmt(c.budget)}` : ''}</span>
                      </div>
                      <div style={{ height:8, background:G.bg, borderRadius:4, overflow:'hidden', position:'relative' }}>
                        <div style={{ height:'100%', width:`${actualPct}%`, background: over ? G.red : (c.color || G.accent), borderRadius:4, opacity:0.85 }} />
                        {budgetPct > 0 && <div style={{ position:'absolute', left:`${budgetPct}%`, top:0, height:'100%', width:2, background:G.text, opacity:0.3 }} />}
                      </div>
                    </div>
                  );
                })}
                {barData.length === 0 && <div style={{ color:G.textMuted, fontSize:12 }}>No data. Import a statement to get started.</div>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TRANSACTIONS VIEW */}
      {view === 'transactions' && (
        <div style={{ background:G.card, borderRadius:G.radius, border:`1px solid ${G.border}`, overflow:'hidden' }}>
          <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
            <thead><tr style={{ borderBottom:`1px solid ${G.border}` }}>
              {['Date','Description','Amount','Type','Category','Source'].map(h => (
                <th key={h} style={{ padding:'10px 12px', textAlign:'left', color:G.textMuted, fontSize:10, fontWeight:600, textTransform:'uppercase' }}>{h}</th>
              ))}</tr></thead>
            <tbody>
              {txns.map(t => (
                <tr key={t.id} style={{ borderBottom:`1px solid ${G.border}` }}>
                  <td style={{ padding:'8px 12px', color:G.textDim }}>{t.date}</td>
                  <td style={{ padding:'8px 12px', maxWidth:200, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{t.description}</td>
                  <td style={{ padding:'8px 12px', fontFamily:G.mono, color: t.type==='debit' ? G.red : G.green }}>{t.type==='debit'?'-':'+'}{fmt(t.amount)}</td>
                  <td style={{ padding:'8px 12px' }}><span style={{ padding:'2px 6px', borderRadius:4, background: t.type==='debit' ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)', color: t.type==='debit' ? G.red : G.green, fontSize:10 }}>{t.type}</span></td>
                  <td style={{ padding:'8px 12px', fontSize:11 }}>{catMap[t.category_id]?.icon} {catMap[t.category_id]?.name || '—'}</td>
                  <td style={{ padding:'8px 12px', fontSize:10, color:G.textMuted }}>{t.source}</td>
                </tr>
              ))}
              {txns.length === 0 && <tr><td colSpan={6} style={{ padding:20, textAlign:'center', color:G.textMuted }}>No transactions for {month}. Import a statement to get started.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {/* IMPORTS VIEW */}
      {view === 'imports' && (
        <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
          {imports.map(imp => (
            <div key={imp.id} style={{ background:G.card, borderRadius:G.radius, padding:16, border:`1px solid ${G.border}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <div>
                <div style={{ fontWeight:500, fontSize:13 }}>{imp.source_name || imp.source_type} — {imp.file_name}</div>
                <div style={{ fontSize:11, color:G.textDim, marginTop:2 }}>
                  {imp.transaction_count} transactions · {imp.date_range_start} to {imp.date_range_end} · Imported {imp.created_at?.slice(0,10)}
                </div>
                {imp.summary && <div style={{ fontSize:11, color:G.textMuted, marginTop:2, fontFamily:G.mono }}>
                  Debits: {fmt(imp.summary.total_debit)} · Credits: {fmt(imp.summary.total_credit)}
                </div>}
              </div>
              <button onClick={async () => { await api.deleteBudgetImport(imp.id); loadImports(); }}
                style={{ background:'none', border:'none', color:G.red, fontSize:14, cursor:'pointer', opacity:0.6 }}>✕</button>
            </div>
          ))}
          {imports.length === 0 && <div style={{ textAlign:'center', padding:40, color:G.textMuted }}>No imports yet. Upload a bank statement CSV to get started.</div>}
        </div>
      )}

      {/* CATEGORIES VIEW */}
      {view === 'categories' && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(200px, 1fr))', gap:10 }}>
          {categories.map(c => (
            <div key={c.id} style={{ background:G.card, borderRadius:G.radius, padding:14, border:`1px solid ${G.border}`, borderLeft:`3px solid ${c.color}` }}>
              <div style={{ fontWeight:500, fontSize:13 }}>{c.icon} {c.name}</div>
              <div style={{ fontSize:10, color:G.textMuted, marginTop:2 }}>{c.is_income ? 'Income' : 'Expense'}{c.is_system ? ' · System' : ''}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   MAIN APP
   ═══════════════════════════════════════════════════════════════ */
export default function App() {
  const [user, setUser] = useState(null);
  const [tab, setTab] = useState('overview');
  const [holdings, setHoldings] = useState([]);
  const [portfolio, setPortfolio] = useState({ members: [], goals: [], alerts: [] });
  const [showAddHolding, setShowAddHolding] = useState(false);
  const [txnHolding, setTxnHolding] = useState(null);
  const [loading, setLoading] = useState(true);

  // Check existing session
  useEffect(() => {
    const stored = localStorage.getItem('wl_user');
    const token = getToken();
    if (stored && token) {
      setUser(JSON.parse(stored));
      loadData();
    } else {
      setLoading(false);
    }
  }, []);

  const loadData = async () => {
    try {
      const [h, p] = await Promise.all([api.getHoldings(), api.getPortfolio()]);
      setHoldings(h);
      setPortfolio(p);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const logout = () => { clearToken(); setUser(null); setHoldings([]); setPortfolio({ members:[], goals:[], alerts:[] }); };

  const handleAuth = (res) => { setUser(res); loadData(); };

  const savePortfolio = async (update) => {
    const next = { ...portfolio, ...update };
    setPortfolio(next);
    await api.savePortfolio(next);
  };

  const addHolding = async (data) => {
    const res = await api.createHolding(data);
    setHoldings(prev => [res, ...prev]);
  };

  const deleteHolding = async (id) => {
    if (!confirm('Delete this holding and all transactions?')) return;
    await api.deleteHolding(id);
    setHoldings(prev => prev.filter(h => h.id !== id));
  };

  const refreshPrices = async () => {
    try { await api.refreshPrices(); await loadData(); } catch (e) { alert(e.message); }
  };

  if (!user && !loading) return <AuthScreen onAuth={handleAuth} />;

  const tabs = [
    { key:'overview', icon:'◎', label:'Overview' },
    { key:'holdings', icon:'▦', label:'Holdings' },
    { key:'goals', icon:'◉', label:'Goals' },
    { key:'alerts', icon:'△', label:'Alerts' },
    { key:'members', icon:'◇', label:'Members' },
    { key:'advisor', icon:'✶', label:'Advisor' },
    { key:'budget', icon:'₹', label:'Budget' },
  ];

  const trigCount = portfolio.alerts.filter(a => {
    if (!a.active) return false;
    const allCur = holdings.reduce((s, h) => s + getVal(h), 0);
    const allInv = holdings.reduce((s, h) => s + getInv(h), 0);
    if (a.type === 'RETURN_TARGET') return allInv > 0 && ((allCur - allInv) / allInv * 100) < a.threshold;
    const tv = holdings.filter(h => h.type === a.assetType).reduce((s, h) => s + getVal(h), 0);
    const tp = allCur > 0 ? (tv / allCur) * 100 : 0;
    return a.type === 'ALLOCATION_DRIFT' ? tp > a.threshold : tp < a.threshold;
  }).length;

  return (
    <>
      <style>{globalCSS}</style>
      {loading ? (
        <div style={{ minHeight:'100vh', display:'flex', alignItems:'center', justifyContent:'center' }}>
          <div style={{ textAlign:'center', animation:'pulse 1.5s infinite' }}>
            <div style={{ fontSize:48, marginBottom:12 }}>🔐</div>
            <div style={{ color:G.textDim, fontSize:13 }}>Decrypting your vault...</div>
          </div>
        </div>
      ) : (
        <div style={{ display:'flex', minHeight:'100vh' }}>
          {/* Sidebar */}
          <nav style={{ width:220, background:G.card, borderRight:`1px solid ${G.border}`, padding:'20px 0', flexShrink:0,
            display:'flex', flexDirection:'column' }}>
            <div style={{ padding:'0 20px 24px', borderBottom:`1px solid ${G.border}`, marginBottom:12 }}>
              <div style={{ fontSize:18, fontWeight:700 }}>🔐 WealthLens</div>
              <div style={{ fontSize:10, color:G.accent, letterSpacing:'0.1em', marginTop:2 }}>ZERO-KNOWLEDGE VAULT</div>
            </div>
            <div style={{ flex:1 }}>
              {tabs.map(t => (
                <button key={t.key} onClick={() => setTab(t.key)}
                  style={{ display:'flex', alignItems:'center', gap:10, width:'100%', padding:'10px 20px', border:'none',
                    background: tab === t.key ? G.accentGlow : 'transparent',
                    color: tab === t.key ? G.accent : G.textDim, fontSize:13, fontWeight: tab === t.key ? 600 : 400,
                    borderRight: tab === t.key ? `2px solid ${G.accent}` : '2px solid transparent', textAlign:'left' }}>
                  <span style={{ fontSize:16, width:20, textAlign:'center' }}>{t.icon}</span>
                  {t.label}
                  {t.key === 'alerts' && trigCount > 0 && (
                    <span style={{ marginLeft:'auto', background:G.red, color:'#fff', fontSize:10, fontWeight:700, padding:'1px 6px', borderRadius:10 }}>{trigCount}</span>
                  )}
                </button>
              ))}
            </div>
            <div style={{ padding:'16px 20px', borderTop:`1px solid ${G.border}` }}>
              <div style={{ fontSize:12, color:G.textDim, marginBottom:4 }}>{user?.display_name || user?.email}</div>
              <button onClick={logout} style={{ background:'none', border:'none', color:G.textMuted, fontSize:11, cursor:'pointer' }}>Sign Out</button>
            </div>
          </nav>

          {/* Main content */}
          <main style={{ flex:1, padding:'24px 32px', overflow:'auto' }}>
            <div style={{ maxWidth:1100, margin:'0 auto' }}>
              {tab === 'overview' && <OverviewTab holdings={holdings} members={portfolio.members} goals={portfolio.goals} alerts={portfolio.alerts} />}
              {tab === 'holdings' && <HoldingsTab holdings={holdings} members={portfolio.members}
                onAdd={() => setShowAddHolding(true)} onDelete={deleteHolding} onRefresh={refreshPrices}
                onTxnOpen={h => setTxnHolding(h)} />}
              {tab === 'goals' && <GoalsTab goals={portfolio.goals} holdings={holdings} members={portfolio.members}
                onSave={goals => savePortfolio({ goals })} />}
              {tab === 'alerts' && <AlertsTab alerts={portfolio.alerts} holdings={holdings}
                onSave={alerts => savePortfolio({ alerts })} />}
              {tab === 'members' && <MembersTab members={portfolio.members} holdings={holdings}
                onSave={members => savePortfolio({ members })} />}
              {tab === 'advisor' && <AdvisorTab holdings={holdings} members={portfolio.members} goals={portfolio.goals} alerts={portfolio.alerts} />}
              {tab === 'budget' && <BudgetTab />}
            </div>
          </main>

          {/* Modals */}
          <AddHoldingModal open={showAddHolding} onClose={() => setShowAddHolding(false)}
            members={portfolio.members} onAdd={addHolding} />
          <TransactionPanel holding={txnHolding} onClose={() => setTxnHolding(null)} onReload={loadData} />
        </div>
      )}
    </>
  );
}
