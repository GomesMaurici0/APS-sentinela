import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Fingerprint, History as HistoryIcon, ScanFace, ShieldCheck, Users as UsersIcon } from 'lucide-react';
import { api, Stats } from './api';
import { Camera } from './Camera';
import { Users } from './Users';
import { History } from './History';
import './style.css';

type Tab = 'terminal' | 'users' | 'history';
const titles = { terminal: ['Terminal de acesso', 'Identificação facial e autorização por permissão.'], users: ['Gestão de usuários', 'Cadastro, permissões e referências faciais.'], history: ['Histórico de acessos', 'Rastreabilidade das decisões do terminal.'] };

function App() {
  const [tab, setTab] = useState<Tab>('terminal');
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState('');

  async function refresh() {
    try { setStats(await api<Stats>('/stats')); setUpdated(new Date().toLocaleTimeString('pt-BR')); }
    catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { void refresh(); }, []);
  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="#terminal" onClick={() => setTab('terminal')}><Fingerprint size={32} /><span>SENTINELA<small>Controle de acesso biométrico</small></span></a>
      <nav aria-label="Navegação principal">{([
        ['terminal', ScanFace, 'Terminal de acesso'], ['users', UsersIcon, 'Usuários'], ['history', HistoryIcon, 'Histórico'],
      ] as const).map(([value, Icon, name]) => <button key={value} className={tab === value ? 'nav-item selected' : 'nav-item'} onClick={() => { setTab(value); setError(''); }} aria-current={tab === value ? 'page' : undefined}><Icon size={20} />{name}</button>)}</nav>
      <div className="sidebar-bottom"><div className="local-note"><ShieldCheck size={19} /><div>Execução local<small>Sem serviços externos</small></div></div></div>
    </aside>
    <main><header className="page-header"><div><p className="eyebrow">SENTINELA / APS</p><h1>{titles[tab][0]}</h1><p className="muted">{titles[tab][1]}</p></div><span className="prototype-label">Protótipo acadêmico</span></header>
      <div className="stats-strip" aria-label="Indicadores do sistema"><div><strong>{stats?.users ?? '—'}</strong><span>Usuários</span></div><div><strong>{stats?.enrolled ?? '—'}</strong><span>Com biometria</span></div><div><strong>{stats?.granted ?? '—'}</strong><span>Autorizados</span></div><div><strong>{stats?.denied ?? '—'}</strong><span>Negados</span></div><small>{updated ? `Atualizado às ${updated}` : 'Consultando indicadores…'}</small></div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="main-content">{tab === 'terminal' ? <Camera onAttempt={refresh} /> : tab === 'users' ? <Users onChanged={refresh} /> : <History />}</div>
      <footer><span>Identificação não comprova vivacidade.</span><span>Dados biométricos protegidos no computador local.</span></footer>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App />);
