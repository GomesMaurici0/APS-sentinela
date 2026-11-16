import {useEffect, useState} from 'react';
import {RefreshCw} from 'lucide-react';
import {requisitarApi, Attempt, formatarData, traduzirMotivo, Page} from './api';

export function Historico() {
    const [pagina, definirPagina] = useState<Page<Attempt>>({items: [], total: 0, offset: 0, limit: 20});
    const [filtro, definirFiltro] = useState('');
    const [deslocamento, definirDeslocamento] = useState(0);
    const [erro, definirErro] = useState('');
    const [processando, definirProcessando] = useState(false);

    async function carregar() {
        definirProcessando(true);
        definirErro('');
        try {
            definirPagina(await requisitarApi(`/attempts?offset=${deslocamento}&limit=20${filtro ? `&granted=${filtro}` : ''}`));
        } catch (evento) {
            definirErro((evento as Error).message);
        } finally {
            definirProcessando(false);
        }
    }

    useEffect(() => {
        void carregar();
    }, [filtro, deslocamento]);
    return <>
        <div className="section-heading">
            <div><h2>Tentativas de acesso</h2><p className="muted">Decisões persistidas, com motivo e tempo de
                processamento.</p></div>
            <button className="secondary" onClick={carregar} disabled={processando}><RefreshCw size={16}/> Atualizar</button>
        </div>
        <div className="history-filter"><label>Resultado<select value={filtro} onChange={evento => {
            definirFiltro(evento.target.value);
            definirDeslocamento(0);
        }}>
            <option value="">Todos os resultados</option>
            <option value="true">Autorizados</option>
            <option value="false">Negados</option>
        </select></label><p className="hint">Imagens e embeddings não fazem parte do histórico.</p></div>
        {erro && <p className="error" role="alert">{erro}</p>}
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
                {pagina.items.map(tentativa => <tr key={tentativa.id}>
                    <td><strong>#{tentativa.id}</strong><small>{formatarData(tentativa.occurred_at)}</small></td>
                    <td>{tentativa.subject_id ?? 'Não identificada / excluída'}</td>
                    <td>Nível {tentativa.requested_level}<small>{tentativa.division ?? (tentativa.requested_level === 3 ? 'Cofre' : 'Geral')}</small>
                    </td>
                    <td><span
                        className={`badge ${tentativa.granted ? 'positive' : 'negative'}`}>{tentativa.granted ? 'Autorizado' : 'Negado'}</span>
                    </td>
                    <td>{traduzirMotivo(tentativa.reason)}{tentativa.similarity !== null &&
                        <small>Similaridade {tentativa.similarity.toFixed(3)}</small>}</td>
                    <td>{tentativa.elapsed_ms.toFixed(0)} ms</td>
                </tr>)}
                </tbody>
            </table>
            {!pagina.items.length &&
                <div className="empty-state"><h3>{processando ? 'Carregando histórico…' : 'Nenhuma tentativa encontrada'}</h3>
                    <p>As avaliações feitas no terminal serão registradas aqui.</p></div>}</div>
        <div className="pagination"><span>{pagina.total} tentativa(s)</span>
            <div className="actions">
                <button className="secondary" disabled={deslocamento === 0 || processando}
                        onClick={() => definirDeslocamento(Math.max(0, deslocamento - 20))}>Anterior
                </button>
                <button className="secondary" disabled={deslocamento + 20 >= pagina.total || processando}
                        onClick={() => definirDeslocamento(deslocamento + 20)}>Próxima
                </button>
            </div>
        </div>
    </>;
}
