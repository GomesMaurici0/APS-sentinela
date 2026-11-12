import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowRight, Fingerprint, History as HistoryIcon, LockKeyhole, LogOut, ScanFace, ShieldCheck, Users as UsersIcon } from 'lucide-react';
import { api, Session, setSession, Stats } from './api';
import { Camera } from './Camera';
import { Users } from './Users';
import { History } from './History';
import './style.css';

type Tab = 'terminal' | 'users' | 'history';
const titles = { terminal: ['Terminal de acesso', 'Identificação facial e autorização por permissão.'], users: ['Gestão de usuários', 'Cadastros e referências sob controle administrativo.'], history: ['Histórico de acessos', 'Rastreabilidade das decisões do terminal.'] };

function App() {
  const [session, updateSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('terminal');
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState('');

  function signedIn(value: Session | null) { setSession(value); updateSession(value); }
  useEffect(() => {
    const expired = () => { signedIn(null); setError('Sessão expirada. Entre novamente.'); };
    window.addEventListener('session-expired', expired);
    api<Session>('/auth/session').then(signedIn).catch(() => signedIn(null)).finally(() => setLoading(false));
    return () => window.removeEventListener('session-expired', expired);
  }, []);
  async function refresh() {
    try { setStats(await api<Stats>('/stats')); setUpdated(new Date().toLocaleTimeString('pt-BR')); }
    catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { if (session) void refresh(); }, [session]);
  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => {
      signedIn(null); setError('Sessão expirada. Entre novamente.');
    }, Math.max(0, session.expires_at * 1000 - Date.now()));
    return () => window.clearTimeout(timer);
  }, [session]);
  async function logout() {
    try { await api('/auth/logout', 'POST'); signedIn(null); setStats(null); setError(''); }
    catch (e) { setError((e as Error).message); }
  }
  if (loading) return <div className="loading-screen" role="status"><Fingerprint size={40} /> Carregando sessão local…</div>;
  if (!session) return <Login onLogin={value => { signedIn(value); setError(''); }} message={error} />;
  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="#terminal" onClick={() => setTab('terminal')}><Fingerprint size={32} /><span>SENTINELA<small>Controle de acesso biométrico</small></span></a>
      <nav aria-label="Navegação principal">{([
        ['terminal', ScanFace, 'Terminal de acesso'], ['users', UsersIcon, 'Usuários'], ['history', HistoryIcon, 'Histórico'],
      ] as const).map(([value, Icon, name]) => <button key={value} className={tab === value ? 'nav-item selected' : 'nav-item'} onClick={() => { setTab(value); setError(''); }} aria-current={tab === value ? 'page' : undefined}><Icon size={20} />{name}</button>)}</nav>
      <div className="sidebar-bottom"><div className="local-note"><ShieldCheck size={19} /><div>Execução local<small>Sem serviços externos</small></div></div>
        <div className="account"><span><strong>{session.username}</strong><small>Administrador</small></span><button className="quiet" onClick={logout} aria-label="Sair da conta"><LogOut size={19} /></button></div></div>
    </aside>
    <main><header className="page-header"><div><p className="eyebrow">SENTINELA / APS</p><h1>{titles[tab][0]}</h1><p className="muted">{titles[tab][1]}</p></div><span className="prototype-label">Protótipo acadêmico</span></header>
      <div className="stats-strip" aria-label="Indicadores do sistema"><div><strong>{stats?.users ?? '—'}</strong><span>Usuários</span></div><div><strong>{stats?.enrolled ?? '—'}</strong><span>Com biometria</span></div><div><strong>{stats?.granted ?? '—'}</strong><span>Autorizados</span></div><div><strong>{stats?.denied ?? '—'}</strong><span>Negados</span></div><small>{updated ? `Atualizado às ${updated}` : 'Consultando indicadores…'}</small></div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="main-content">{tab === 'terminal' ? <Camera onAttempt={refresh} /> : tab === 'users' ? <Users onChanged={refresh} /> : <History />}</div>
      <footer><span>Identificação não comprova vivacidade.</span><span>Dados biométricos protegidos no computador local.</span></footer>
    </main>
  </div>;
}

function Login({ onLogin, message }: { onLogin: (value: Session) => void; message: string }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { onLogin(await api<Session>('/auth/login', 'POST', { username, password })); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <main className="login-page"><div className="login-story"><div className="brand"><Fingerprint size={34} /><span>SENTINELA<small>Controle de acesso biométrico</small></span></div>
    <div className="login-copy"><ShieldCheck size={52} strokeWidth={1.2} /><h1>Identidade verificada.<br />Permissão respeitada.</h1><p>Reconhecimento facial e controle de acesso em três níveis de segurança.</p></div><small>APS UNIP · Processamento de Imagem e Visão Computacional</small></div>
    <div className="login-form-wrap"><form className="login-form" onSubmit={submit}><LockKeyhole size={28} /><h2>Acesso administrativo</h2><p className="muted">Entre para gerenciar usuários e operar o terminal local.</p>
      <label>Usuário<input autoComplete="username" autoFocus required minLength={3} maxLength={40} value={username} onChange={e => setUsername(e.target.value)} /></label>
      <label>Senha<input type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></label>
      {(error || message) && <p className="error" role="alert">{error || message}</p>}
      <button className="primary wide" disabled={busy}>{busy ? 'Verificando…' : 'Entrar no sistema'}<ArrowRight size={18} /></button>
      <p className="hint">Use a conta criada neste computador pelo responsável pelo projeto.</p></form>
      <p className="login-disclaimer">Protótipo acadêmico. Não destinado à proteção de instalações reais.</p></div></main>;
}

createRoot(document.getElementById('root')!).render(<App />);
