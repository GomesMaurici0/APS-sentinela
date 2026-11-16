import {useEffect, useState} from 'react';
import {Download, Plus, ScanFace, Trash2, X} from 'lucide-react';
import {requisitarApi, Page, Person} from './api';
import {Camera} from './Camera';

type Props = { onChanged: () => void };
const cadastroVazio = {
    subject_id: '',
    display_name: '',
    level: 1,
    divisions: [],
    active: true,
    sample_count: 0,
    consent_at: null
} satisfies Person;

export function Usuarios({onChanged: aoAlterar}: Props) {
    const [pagina, definirPagina] = useState<Page<Person>>({items: [], total: 0, offset: 0, limit: 20});
    const [deslocamento, definirDeslocamento] = useState(0);
    const [pessoa, definirPessoa] = useState<Person | null>(null);
    const [editando, definirEditando] = useState(false);
    const [pessoaEmCadastro, definirPessoaEmCadastro] = useState<Person | null>(null);
    const [erro, definirErro] = useState('');
    const [aviso, definirAviso] = useState('');
    const [processando, definirProcessando] = useState(false);
    const [carregando, definirCarregando] = useState(true);

    async function carregar() {
        definirCarregando(true);
        try {
            definirPagina(await requisitarApi<Page<Person>>(`/users?offset=${deslocamento}&limit=20`));
        } catch (evento) {
            definirErro((evento as Error).message);
        } finally {
            definirCarregando(false);
        }
    }

    useEffect(() => {
        void carregar();
    }, [deslocamento]);

    async function excluir(usuario: Person, somenteBiometria = false) {
        if (!window.confirm(somenteBiometria ? `Excluir as referências de ${usuario.display_name}?` : `Excluir ${usuario.display_name}, suas referências e desvincular o histórico?`)) return;
        definirProcessando(true);
        definirErro('');
        definirAviso('');
        try {
            await requisitarApi(`/users/${usuario.subject_id}${somenteBiometria ? '/biometrics' : ''}`, 'DELETE');
            definirAviso(somenteBiometria ? 'Referências excluídas.' : 'Usuário excluído. Histórico desvinculado.');
            definirPessoa(null);
            await carregar();
            aoAlterar();
        } catch (evento) {
            definirErro((evento as Error).message);
        } finally {
            definirProcessando(false);
        }
    }

    async function importarLegado() {
        if (!window.confirm('Importar os cadastros consentidos do laboratório para o painel? Após a gravação, as referências serão removidas da galeria antiga. Encerre antes as janelas do laboratório.')) return;
        definirProcessando(true);
        definirErro('');
        definirAviso('');
        try {
            const resultado = await requisitarApi<{ imported: number; already_present: number }>('/legacy/import', 'POST');
            definirAviso(`${resultado.imported} cadastro(s) importado(s). ${resultado.already_present} já importado(s).`);
            await carregar();
            aoAlterar();
        } catch (evento) {
            definirErro((evento as Error).message);
        } finally {
            definirProcessando(false);
        }
    }

    if (pessoaEmCadastro) return <Camera key={pessoaEmCadastro.subject_id} person={pessoaEmCadastro} onCancel={() => definirPessoaEmCadastro(null)}
                                  onSaved={() => {
                                      definirPessoaEmCadastro(null);
                                      definirAviso('Referências biométricas salvas.');
                                      void carregar();
                                      aoAlterar();
                                  }}/>;

    return <>
        <div className="section-heading">
            <div><h2>Usuários autorizados</h2><p className="muted">Identidade, nível de segurança e divisões
                permitidas.</p></div>
            <div className="actions">
                <button onClick={importarLegado} disabled={processando} className="secondary"><Download size={16}/> Importar
                    laboratório
                </button>
                <button className="primary" onClick={() => {
                    definirPessoa({...cadastroVazio});
                    definirEditando(false);
                    definirErro('');
                }}><Plus size={18}/> Novo usuário
                </button>
            </div>
        </div>
        {erro && <p className="error" role="alert">{erro}</p>}{aviso &&
        <p className="success" role="status">{aviso}</p>}
        {pessoa && <FormularioUsuario key={editando ? pessoa.subject_id : 'new'} person={pessoa} editing={editando}
                             onCancel={() => definirPessoa(null)} onSaved={async usuario => {
            definirPessoa(null);
            definirAviso('Usuário salvo.');
            await carregar();
            aoAlterar();
            if (!editando) definirPessoaEmCadastro(usuario);
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
                <tbody>{pagina.items.map(usuario => <tr key={usuario.subject_id}>
                    <td><strong>{usuario.display_name}</strong><small>{usuario.subject_id}</small></td>
                    <td>Nível {usuario.level}</td>
                    <td>{usuario.level === 3 ? 'Todas' : usuario.divisions.join(', ') || 'Acesso geral'}</td>
                    <td>{usuario.sample_count ? `${usuario.sample_count} referências` :
                        <span className="muted">Não cadastrada</span>}</td>
                    <td><span
                        className={`badge ${usuario.active ? 'positive' : ''}`}>{usuario.active ? 'Ativo' : 'Inativo'}</span>
                    </td>
                    <td>
                        <div className="row-actions">
                            <button className="quiet" disabled={processando} onClick={() => {
                                definirPessoa(usuario);
                                definirEditando(true);
                            }}>Editar
                            </button>
                            <button className="quiet" disabled={processando} onClick={() => definirPessoaEmCadastro(usuario)}
                                    aria-label={`Cadastrar rosto de ${usuario.display_name}`}><ScanFace size={18}/>
                            </button>
                            <button className="quiet danger" disabled={processando} onClick={() => excluir(usuario)}
                                    aria-label={`Excluir ${usuario.display_name}`}><Trash2 size={17}/></button>
                            {usuario.sample_count > 0 &&
                                <button className="quiet" disabled={processando} onClick={() => excluir(usuario, true)}>Excluir
                                    biometria</button>}</div>
                    </td>
                </tr>)}</tbody>
            </table>
            {!pagina.items.length && <div className="empty-state"><ScanFace size={32}/>
                <h3>{carregando ? 'Carregando usuários…' : 'Nenhum usuário nesta página'}</h3><p>Cadastre um voluntário ou
                    importe os registros do laboratório.</p></div>}
        </div>
        <div className="pagination"><span>{pagina.total} usuário(s)</span>
            <div className="actions">
                <button className="secondary" disabled={deslocamento === 0 || carregando}
                        onClick={() => definirDeslocamento(Math.max(0, deslocamento - 20))}>Anterior
                </button>
                <button className="secondary" disabled={deslocamento + 20 >= pagina.total || carregando}
                        onClick={() => definirDeslocamento(deslocamento + 20)}>Próxima
                </button>
            </div>
        </div>
    </>;
}

function FormularioUsuario({person: pessoa, editing: editando, onCancel: aoCancelar, onSaved: aoSalvar}: {
    person: Person;
    editing: boolean;
    onCancel: () => void;
    onSaved: (usuario: Person) => void
}) {
    const [formulario, definirFormulario] = useState(pessoa);
    const [divisoes, definirDivisoes] = useState(pessoa.divisions.join(', '));
    const [erro, definirErro] = useState('');
    const [processando, definirProcessando] = useState(false);

    async function salvar(evento: React.FormEvent) {
        evento.preventDefault();
        definirErro('');
        definirProcessando(true);
        const divisoesPermitidas = formulario.level === 2 ? divisoes.split(',').map(valor => valor.trim()).filter(Boolean) : [];
        if (formulario.level === 2 && !divisoesPermitidas.length) {
            definirErro('Informe pelo menos uma divisão para o diretor.');
            definirProcessando(false);
            return;
        }
        try {
            const dados = {
                display_name: formulario.display_name.trim(),
                level: formulario.level,
                divisions: divisoesPermitidas,
                active: formulario.active
            };
            const usuario = await requisitarApi<Person>(editando ? `/users/${formulario.subject_id}` : '/users', editando ? 'PUT' : 'POST', editando ? dados : {
                ...dados,
                subject_id: formulario.subject_id.trim()
            });
            aoSalvar(usuario);
        } catch (evento) {
            definirErro((evento as Error).message);
        } finally {
            definirProcessando(false);
        }
    }

    return <form className="user-form" onSubmit={salvar}>
        <div className="section-heading"><h3>{editando ? 'Editar usuário' : 'Novo usuário'}</h3>
            <button type="button" className="quiet" disabled={processando} onClick={aoCancelar} aria-label="Fechar formulário"><X
                size={20}/></button>
        </div>
        <div className="form-grid"><label>Identificador fictício<input required pattern="[a-zA-Z0-9_-]{1,40}"
                                                                       maxLength={40} readOnly={editando}
                                                                       value={formulario.subject_id} onChange={evento => definirFormulario({
            ...formulario,
            subject_id: evento.target.value
        })} placeholder="voluntario01"/></label>
            <label>Nome de exibição<input required maxLength={100} value={formulario.display_name}
                                          onChange={evento => definirFormulario({...formulario, display_name: evento.target.value})}/></label>
            <label>Nível<select value={formulario.level} onChange={evento => definirFormulario({...formulario, level: Number(evento.target.value)})}>
                <option value="1">1 — Acesso geral</option>
                <option value="2">2 — Diretor</option>
                <option value="3">3 — Ministro</option>
            </select></label>
            {formulario.level === 2 && <label>Divisões autorizadas<input required value={divisoes}
                                                                   onChange={evento => definirDivisoes(evento.target.value)}
                                                                   placeholder="florestas, aguas"/><small>Separe as
                divisões por vírgula; use os mesmos nomes no terminal.</small></label>}
        </div>
        <label className="check"><input type="checkbox" checked={formulario.active}
                                        onChange={evento => definirFormulario({...formulario, active: evento.target.checked})}/> Usuário
            ativo</label>
        {erro && <p className="error" role="alert">{erro}</p>}
        <div className="actions">
            <button className="primary"
                    disabled={processando}>{processando ? 'Salvando…' : editando ? 'Salvar alterações' : 'Salvar e cadastrar rosto'}</button>
            <button type="button" className="secondary" disabled={processando} onClick={aoCancelar}>Cancelar</button>
        </div>
    </form>;
}
