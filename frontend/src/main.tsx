import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Fingerprint, History as HistoryIcon, ScanFace, ShieldCheck, Users as UsersIcon } from 'lucide-react';
import { requisitarApi, Stats } from './api';
import { Camera } from './Camera';
import { Usuarios } from './Users';
import { Historico } from './History';
import './style.css';

type Tab = 'terminal' | 'users' | 'history';
const titulos = { terminal: ['Terminal de acesso', 'Identificação facial e autorização por permissão.'], users: ['Gestão de usuários', 'Cadastro, permissões e referências faciais.'], history: ['Histórico de acessos', 'Rastreabilidade das decisões do terminal.'] };

function Aplicacao() {
  const [aba, definirAba] = useState<Tab>('terminal');
  const [indicadores, definirIndicadores] = useState<Stats | null>(null);
  const [erro, definirErro] = useState('');
  const [atualizadoEm, definirAtualizadoEm] = useState('');

  async function atualizarIndicadores() {
    try { definirIndicadores(await requisitarApi<Stats>('/stats')); definirAtualizadoEm(new Date().toLocaleTimeString('pt-BR')); }
    catch (evento) { definirErro((evento as Error).message); }
  }
  useEffect(() => { void atualizarIndicadores(); }, []);
  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="#terminal" onClick={() => definirAba('terminal')}><Fingerprint size={32} /><span>SENTINELA<small>Controle de acesso biométrico</small></span></a>
      <nav aria-label="Navegação principal">{([
        ['terminal', ScanFace, 'Terminal de acesso'], ['users', UsersIcon, 'Usuários'], ['history', HistoryIcon, 'Histórico'],
      ] as const).map(([valor, Icon, nome]) => <button key={valor} className={aba === valor ? 'nav-item selected' : 'nav-item'} onClick={() => { definirAba(valor); definirErro(''); }} aria-current={aba === valor ? 'page' : undefined}><Icon size={20} />{nome}</button>)}</nav>
      <div className="sidebar-bottom"><div className="local-note"><ShieldCheck size={19} /><div>Execução local<small>Sem serviços externos</small></div></div></div>
    </aside>
    <main><header className="page-header"><div><p className="eyebrow">SENTINELA / APS</p><h1>{titulos[aba][0]}</h1><p className="muted">{titulos[aba][1]}</p></div><span className="prototype-label">Protótipo acadêmico</span></header>
      <div className="stats-strip" aria-label="Indicadores do sistema"><div><strong>{indicadores?.users ?? '—'}</strong><span>Usuários</span></div><div><strong>{indicadores?.enrolled ?? '—'}</strong><span>Com biometria</span></div><div><strong>{indicadores?.granted ?? '—'}</strong><span>Autorizados</span></div><div><strong>{indicadores?.denied ?? '—'}</strong><span>Negados</span></div><small>{atualizadoEm ? `Atualizado às ${atualizadoEm}` : 'Consultando indicadores…'}</small></div>
      {erro && <p className="error" role="alert">{erro}</p>}
      <div className="main-content">{aba === 'terminal' ? <Camera onAttempt={atualizarIndicadores} /> : aba === 'users' ? <Usuarios onChanged={atualizarIndicadores} /> : <Historico />}</div>
      <footer><span>Identificação não comprova vivacidade.</span><span>Dados biométricos protegidos no computador local.</span></footer>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<Aplicacao />);
