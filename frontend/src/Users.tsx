import {useEffect, useState} from 'react';
import {Download, Plus, ScanFace, Trash2, X} from 'lucide-react';
import {api, Page, Person} from './api';
import {Camera} from './Camera';

type Props = { onChanged: () => void };
const blank = {
    subject_id: '',
    display_name: '',
    level: 1,
    divisions: [],
    active: true,
    sample_count: 0,
    consent_at: null
} satisfies Person;

export function Users({onChanged}: Props) {
    const [page, setPage] = useState<Page<Person>>({items: [], total: 0, offset: 0, limit: 20});
    const [offset, setOffset] = useState(0);
    const [person, setPerson] = useState<Person | null>(null);
    const [editing, setEditing] = useState(false);
    const [enrolling, setEnrolling] = useState<Person | null>(null);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [busy, setBusy] = useState(false);
    const [loading, setLoading] = useState(true);

    async function load() {
        setLoading(true);
        try {
            setPage(await api<Page<Person>>(`/users?offset=${offset}&limit=20`));
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void load();
    }, [offset]);

    async function remove(user: Person, biometricsOnly = false) {
        if (!window.confirm(biometricsOnly ? `Excluir as referências de ${user.display_name}?` : `Excluir ${user.display_name}, suas referências e desvincular o histórico?`)) return;
        setBusy(true);
        setError('');
        setNotice('');
        try {
            await api(`/users/${user.subject_id}${biometricsOnly ? '/biometrics' : ''}`, 'DELETE');
            setNotice(biometricsOnly ? 'Referências excluídas.' : 'Usuário excluído. Histórico desvinculado.');
            setPerson(null);
            await load();
            onChanged();
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }

    async function importLegacy() {
        if (!window.confirm('Importar os cadastros consentidos do laboratório para o painel? Após a gravação, as referências serão removidas da galeria antiga. Encerre antes as janelas do laboratório.')) return;
        setBusy(true);
        setError('');
        setNotice('');
        try {
            const result = await api<{ imported: number; already_present: number }>('/legacy/import', 'POST');
            setNotice(`${result.imported} cadastro(s) importado(s). ${result.already_present} já importado(s).`);
            await load();
            onChanged();
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }

    if (enrolling) return <Camera key={enrolling.subject_id} person={enrolling} onCancel={() => setEnrolling(null)}
                                  onSaved={() => {
                                      setEnrolling(null);
                                      setNotice('Referências biométricas salvas.');
                                      void load();
                                      onChanged();
                                  }}/>;

    return <>
        <div className="section-heading">
            <div><h2>Usuários autorizados</h2><p className="muted">Identidade, nível de segurança e divisões
                permitidas.</p></div>
            <div className="actions">
                <button onClick={importLegacy} disabled={busy} className="secondary"><Download size={16}/> Importar
                    laboratório
                </button>
                <button className="primary" onClick={() => {
                    setPerson({...blank});
                    setEditing(false);
                    setError('');
                }}><Plus size={18}/> Novo usuário
                </button>
            </div>
        </div>
        {error && <p className="error" role="alert">{error}</p>}{notice &&
        <p className="success" role="status">{notice}</p>}
        {person && <UserForm key={editing ? person.subject_id : 'new'} person={person} editing={editing}
                             onCancel={() => setPerson(null)} onSaved={async user => {
            setPerson(null);
            setNotice('Usuário salvo.');
            await load();
            onChanged();
            if (!editing) setEnrolling(user);
        }}/>}
        <div className="table-wrap">
            <table>
                <thead>
                <tr>
                    <th>Identificação</th>
                    <th>Permissão</th>
                    <th>Divisões</th>
                    <th>Biometria</th>
                    <th>Estado</th>
                    <th>Ações</th>
                </tr>
                </thead>
                <tbody>{page.items.map(user => <tr key={user.subject_id}>
                    <td><strong>{user.display_name}</strong><small>{user.subject_id}</small></td>
                    <td>Nível {user.level}</td>
                    <td>{user.level === 3 ? 'Todas' : user.divisions.join(', ') || 'Acesso geral'}</td>
                    <td>{user.sample_count ? `${user.sample_count} referências` :
                        <span className="muted">Não cadastrada</span>}</td>
                    <td><span
                        className={`badge ${user.active ? 'positive' : ''}`}>{user.active ? 'Ativo' : 'Inativo'}</span>
                    </td>
                    <td>
                        <div className="row-actions">
                            <button className="quiet" disabled={busy} onClick={() => {
                                setPerson(user);
                                setEditing(true);
                            }}>Editar
                            </button>
                            <button className="quiet" disabled={busy} onClick={() => setEnrolling(user)}
                                    aria-label={`Cadastrar rosto de ${user.display_name}`}><ScanFace size={18}/>
                            </button>
                            <button className="quiet danger" disabled={busy} onClick={() => remove(user)}
                                    aria-label={`Excluir ${user.display_name}`}><Trash2 size={17}/></button>
                            {user.sample_count > 0 &&
                                <button className="quiet" disabled={busy} onClick={() => remove(user, true)}>Excluir
                                    biometria</button>}</div>
                    </td>
                </tr>)}</tbody>
            </table>
            {!page.items.length && <div className="empty-state"><ScanFace size={32}/>
                <h3>{loading ? 'Carregando usuários…' : 'Nenhum usuário nesta página'}</h3><p>Cadastre um voluntário ou
                    importe os registros do laboratório.</p></div>}
        </div>
        <div className="pagination"><span>{page.total} usuário(s)</span>
            <div className="actions">
                <button className="secondary" disabled={offset === 0 || loading}
                        onClick={() => setOffset(Math.max(0, offset - 20))}>Anterior
                </button>
                <button className="secondary" disabled={offset + 20 >= page.total || loading}
                        onClick={() => setOffset(offset + 20)}>Próxima
                </button>
            </div>
        </div>
    </>;
}

function UserForm({person, editing, onCancel, onSaved}: {
    person: Person;
    editing: boolean;
    onCancel: () => void;
    onSaved: (user: Person) => void
}) {
    const [form, setForm] = useState(person);
    const [divisions, setDivisions] = useState(person.divisions.join(', '));
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);

    async function save(e: React.FormEvent) {
        e.preventDefault();
        setError('');
        setBusy(true);
        const allowed = form.level === 2 ? divisions.split(',').map(value => value.trim()).filter(Boolean) : [];
        if (form.level === 2 && !allowed.length) {
            setError('Informe pelo menos uma divisão para o diretor.');
            setBusy(false);
            return;
        }
        try {
            const values = {
                display_name: form.display_name.trim(),
                level: form.level,
                divisions: allowed,
                active: form.active
            };
            const user = await api<Person>(editing ? `/users/${form.subject_id}` : '/users', editing ? 'PUT' : 'POST', editing ? values : {
                ...values,
                subject_id: form.subject_id.trim()
            });
            onSaved(user);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }

    return <form className="user-form" onSubmit={save}>
        <div className="section-heading"><h3>{editing ? 'Editar usuário' : 'Novo usuário'}</h3>
            <button type="button" className="quiet" disabled={busy} onClick={onCancel} aria-label="Fechar formulário"><X
                size={20}/></button>
        </div>
        <div className="form-grid"><label>Identificador fictício<input required pattern="[a-zA-Z0-9_-]{1,40}"
                                                                       maxLength={40} readOnly={editing}
                                                                       value={form.subject_id} onChange={e => setForm({
            ...form,
            subject_id: e.target.value
        })} placeholder="voluntario01"/></label>
            <label>Nome de exibição<input required maxLength={100} value={form.display_name}
                                          onChange={e => setForm({...form, display_name: e.target.value})}/></label>
            <label>Nível<select value={form.level} onChange={e => setForm({...form, level: Number(e.target.value)})}>
                <option value="1">1 — Acesso geral</option>
                <option value="2">2 — Diretor</option>
                <option value="3">3 — Ministro</option>
            </select></label>
            {form.level === 2 && <label>Divisões autorizadas<input required value={divisions}
                                                                   onChange={e => setDivisions(e.target.value)}
                                                                   placeholder="florestas, aguas"/><small>Separe as
                divisões por vírgula; use os mesmos nomes no terminal.</small></label>}
        </div>
        <label className="check"><input type="checkbox" checked={form.active}
                                        onChange={e => setForm({...form, active: e.target.checked})}/> Usuário
            ativo</label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="actions">
            <button className="primary"
                    disabled={busy}>{busy ? 'Salvando…' : editing ? 'Salvar alterações' : 'Salvar e cadastrar rosto'}</button>
            <button type="button" className="secondary" disabled={busy} onClick={onCancel}>Cancelar</button>
        </div>
    </form>;
}
