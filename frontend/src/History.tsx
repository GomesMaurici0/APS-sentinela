import {useEffect, useState} from 'react';
import {RefreshCw} from 'lucide-react';
import {api, Attempt, date, label, Page} from './api';

export function History() {
    const [page, setPage] = useState<Page<Attempt>>({items: [], total: 0, offset: 0, limit: 20});
    const [filter, setFilter] = useState('');
    const [offset, setOffset] = useState(0);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);

    async function load() {
        setBusy(true);
        setError('');
        try {
            setPage(await api(`/attempts?offset=${offset}&limit=20${filter ? `&granted=${filter}` : ''}`));
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }

    useEffect(() => {
        void load();
    }, [filter, offset]);
    return <>
        <div className="section-heading">
            <div><h2>Tentativas de acesso</h2><p className="muted">Decisões persistidas, com motivo e tempo de
                processamento.</p></div>
            <button className="secondary" onClick={load} disabled={busy}><RefreshCw size={16}/> Atualizar</button>
        </div>
        <div className="history-filter"><label>Resultado<select value={filter} onChange={e => {
            setFilter(e.target.value);
            setOffset(0);
        }}>
            <option value="">Todos os resultados</option>
            <option value="true">Autorizados</option>
            <option value="false">Negados</option>
        </select></label><p className="hint">Imagens e embeddings não fazem parte do histórico.</p></div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="table-wrap">
            <table>
                <thead>
                <tr>
                    <th>Registro</th>
                    <th>Identidade</th>
                    <th>Recurso</th>
                    <th>Resultado</th>
                    <th>Motivo</th>
                    <th>Tempo</th>
                </tr>
                </thead>
                <tbody>
                {page.items.map(item => <tr key={item.id}>
                    <td><strong>#{item.id}</strong><small>{date(item.occurred_at)}</small></td>
                    <td>{item.subject_id ?? 'Não identificada / excluída'}</td>
                    <td>Nível {item.requested_level}<small>{item.division ?? (item.requested_level === 3 ? 'Cofre' : 'Geral')}</small>
                    </td>
                    <td><span
                        className={`badge ${item.granted ? 'positive' : 'negative'}`}>{item.granted ? 'Autorizado' : 'Negado'}</span>
                    </td>
                    <td>{label(item.reason)}{item.similarity !== null &&
                        <small>Similaridade {item.similarity.toFixed(3)}</small>}</td>
                    <td>{item.elapsed_ms.toFixed(0)} ms</td>
                </tr>)}
                </tbody>
            </table>
            {!page.items.length &&
                <div className="empty-state"><h3>{busy ? 'Carregando histórico…' : 'Nenhuma tentativa encontrada'}</h3>
                    <p>As avaliações feitas no terminal serão registradas aqui.</p></div>}</div>
        <div className="pagination"><span>{page.total} tentativa(s)</span>
            <div className="actions">
                <button className="secondary" disabled={offset === 0 || busy}
                        onClick={() => setOffset(Math.max(0, offset - 20))}>Anterior
                </button>
                <button className="secondary" disabled={offset + 20 >= page.total || busy}
                        onClick={() => setOffset(offset + 20)}>Próxima
                </button>
            </div>
        </div>
    </>;
}
