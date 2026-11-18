import {useEffect, useRef, useState} from 'react';
import {Camera as CameraIcon, CameraOff, ScanFace, X} from 'lucide-react';
import {requisitarApi, Attempt, Capture, traduzirMotivo, Person} from './api';

type Props = { person?: Person; onSaved?: () => void; onCancel?: () => void; onAttempt?: () => void };

export function Camera({person: pessoa, onSaved: aoSalvar, onCancel: aoCancelar, onAttempt: aoAvaliar}: Props) {
  const referenciaVideo = useRef<HTMLVideoElement>(null);
  const fluxoCamera = useRef<MediaStream | null>(null);
  const geracaoCaptura = useRef(0);
  const componenteAtivo = useRef(true);
  const requisicaoPendente = useRef(false);
  const [cameraAtiva, definirCameraAtiva] = useState(false);
  const [erro, definirErro] = useState('');
  const [processando, definirProcessando] = useState(false);
  const [imagens, definirImagens] = useState<string[]>([]);
  const [captura, definirCaptura] = useState<Capture | null>(null);
  const [imagemCongelada, definirImagemCongelada] = useState<string | null>(null);
  const [decisao, definirDecisao] = useState<Attempt | null>(null);
  const [nivel, definirNivel] = useState(1);
  const [divisao, definirDivisao] = useState('');
  const [consentimento, definirConsentimento] = useState(false);

  function pararCamera() {
    geracaoCaptura.current++;
    fluxoCamera.current?.getTracks().forEach(trilha => trilha.stop());
    fluxoCamera.current = null;
    definirCameraAtiva(false);
    definirImagemCongelada(null);
    definirImagens([]);
    definirCaptura(null);
    definirDecisao(null);
  }

  useEffect(() => {
    componenteAtivo.current = true;
    return () => {
      componenteAtivo.current = false;
      geracaoCaptura.current++;
      fluxoCamera.current?.getTracks().forEach(trilha => trilha.stop());
    };
  }, []);

  async function iniciarCamera() {
    definirErro('');
    const idCaptura = ++geracaoCaptura.current;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Câmera indisponível. Abra pelo endereço local indicado.');
      const midia = await navigator.mediaDevices.getUserMedia({video: {width: 640, height: 480}, audio: false});
      if (!componenteAtivo.current || idCaptura !== geracaoCaptura.current) {
        midia.getTracks().forEach(trilha => trilha.stop());
        return;
      }
      fluxoCamera.current = midia;
      if (referenciaVideo.current) {
        referenciaVideo.current.srcObject = midia;
        await referenciaVideo.current.play();
      }
      midia.getVideoTracks()[0].addEventListener('ended', () => {
        if (componenteAtivo.current && geracaoCaptura.current === idCaptura) {
          pararCamera();
          definirErro('A câmera foi desconectada. Inicie novamente.');
        }
      });
      definirCameraAtiva(true);
    } catch (evento) {
      fluxoCamera.current?.getTracks().forEach(trilha => trilha.stop());
      fluxoCamera.current = null;
      if (componenteAtivo.current) definirErro(evento instanceof DOMException ? 'Não foi possível abrir a câmera. Verifique a permissão e outros aplicativos.' : (evento as Error).message);
    }
  }

  async function capturarQuadro() {
    if (requisicaoPendente.current || !referenciaVideo.current || !cameraAtiva) return;
    const videoOrigem = referenciaVideo.current;
    if (!videoOrigem.videoWidth) {
      definirErro('Aguarde a câmera iniciar.');
      return;
    }
    if (!pessoa && nivel === 2 && !divisao.trim()) {
      definirErro('Informe a divisão solicitada.');
      return;
    }
    const telaCaptura = document.createElement('canvas');
    const escala = Math.min(1, 640 / Math.max(videoOrigem.videoWidth, videoOrigem.videoHeight));
    telaCaptura.width = Math.round(videoOrigem.videoWidth * escala);
    telaCaptura.height = Math.round(videoOrigem.videoHeight * escala);
    telaCaptura.getContext('2d')!.drawImage(videoOrigem, 0, 0, telaCaptura.width, telaCaptura.height);
    const imagem = telaCaptura.toDataURL('image/jpeg', .85).split(',')[1];
    const idCaptura = geracaoCaptura.current;
    requisicaoPendente.current = true;
    definirProcessando(true);
    definirErro('');
    definirDecisao(null);
    definirCaptura(null);
    definirImagemCongelada(null);
    try {
      if (pessoa) {
        const valor = await requisitarApi<Capture>('/biometrics/analyze', 'POST', {image: imagem});
        if (!componenteAtivo.current || geracaoCaptura.current !== idCaptura) return;
        definirCaptura(valor);
        definirImagemCongelada(imagem);
        if (valor.status === 'ok') definirImagens(anteriores => [...anteriores, imagem]);
        else definirErro(traduzirMotivo(valor.status));
      } else {
        const valor = await requisitarApi<Attempt>('/attempts', 'POST', {
          image: imagem, requested_level: nivel, division: nivel === 2 ? divisao.trim() : null,
        });
        if (!componenteAtivo.current || geracaoCaptura.current !== idCaptura) return;
        definirDecisao(valor);
        definirCaptura(valor.capture ?? null);
        definirImagemCongelada(imagem);
      }
    } catch (evento) {
      if (componenteAtivo.current && geracaoCaptura.current === idCaptura) definirErro((evento as Error).message);
    } finally {
      requisicaoPendente.current = false;
      if (componenteAtivo.current) {
        definirProcessando(false);
        if (!pessoa) aoAvaliar?.();
      }
    }
  }

  async function salvar() {
    if (!pessoa || requisicaoPendente.current) return;
    requisicaoPendente.current = true;
    definirProcessando(true);
    definirErro('');
    try {
      await requisitarApi(`/users/${pessoa.subject_id}/biometrics`, 'POST', {images: imagens, consent: consentimento});
      if (componenteAtivo.current) {
        pararCamera();
        aoSalvar?.();
      }
    } catch (evento) {
      if (componenteAtivo.current) definirErro((evento as Error).message);
    } finally {
      requisicaoPendente.current = false;
      if (componenteAtivo.current) definirProcessando(false);
    }
  }

  return <section className="camera-workspace">
    <div className="camera-column">
      <div className="section-heading"><h2>{pessoa ? `Referências de ${pessoa.display_name}` : 'Captura facial'}</h2>
        {cameraAtiva && <button className="quiet" onClick={pararCamera} disabled={processando}><CameraOff size={16}/> Desligar</button>}
      </div>
      <div className="viewfinder">
        <video ref={referenciaVideo} autoPlay muted playsInline className={cameraAtiva && !imagemCongelada ? '' : 'invisible'}/>
        {imagemCongelada && <img className="capture-image" src={`data:image/jpeg;base64,${imagemCongelada}`}
                        alt="Última captura, mantida somente em memória"/>}
        {imagemCongelada && captura?.width && captura.height &&
            <svg className="face-overlay" viewBox={`0 0 ${captura.width} ${captura.height}`}
                 aria-label="Localização facial">
              {captura.faces.map((rosto, indiceRosto) => <g key={indiceRosto}>
                <rect x={rosto[0]} y={rosto[1]} width={rosto[2]} height={rosto[3]}/>
                {[4, 6, 8, 10, 12].map(indice => <circle key={indice} cx={rosto[indice]} cy={rosto[indice + 1]} r="2"/>)}
              </g>)}
            </svg>}
        {!cameraAtiva &&
            <div className="camera-empty"><ScanFace size={56} strokeWidth={1}/><h3>Câmera desligada</h3><p>Ative para
              enquadrar um rosto.<br/>As imagens não serão gravadas.</p></div>}
        <span
            className="viewfinder-label">{cameraAtiva ? (imagemCongelada ? 'Última captura' : 'Prévia local') : 'Captura sob demanda'}</span>
      </div>
      <div className="camera-actions">
        {!cameraAtiva ?
            <button className="primary" onClick={iniciarCamera} disabled={!!pessoa && !consentimento}><CameraIcon size={18}/> Ativar
              câmera</button>
            : imagemCongelada ? <button className="primary" onClick={() => {
                  definirImagemCongelada(null);
                  definirCaptura(null);
                  definirErro('');
                  definirDecisao(null);
                }} disabled={processando || (!!pessoa && imagens.length >= 5)}>Retomar câmera</button>
                :
                <button className="primary" onClick={capturarQuadro} disabled={processando || (!!pessoa && imagens.length >= 5)}><ScanFace
                    size={18}/>{processando ? 'Processando…' : pessoa ? 'Coletar amostra' : 'Avaliar acesso'}</button>}
        {pessoa && <button className="quiet" onClick={() => {
          pararCamera();
          aoCancelar?.();
        }} disabled={processando}><X size={16}/> Cancelar cadastro</button>}
      </div>
      <p className="hint">Uma captura por ação. Mantenha o rosto inteiro, com boa iluminação.</p>
    </div>
    <div className="decision-column">
      {pessoa ? <>
        <h2>Cadastro biométrico</h2><p className="muted">Colete cinco amostras com pequenas variações de pose. O
        cadastro só é salvo ao confirmar.</p>
        <label className="check"><input type="checkbox" checked={consentimento} disabled={cameraAtiva || processando}
                                        onChange={evento => definirConsentimento(evento.target.checked)}/>
          O voluntário consentiu com o processamento facial local para a APS e foi informado sobre a exclusão e as
          limitações.</label>
        <div className="sample-progress"><strong>{imagens.length} <span>/ 5 amostras</span></strong>
          <progress max="5" value={imagens.length}/>
        </div>
        <div className="sample-strip">{imagens.map((imagem, indice) => <img key={indice}
                                                                         src={`data:image/jpeg;base64,${imagem}`}
                                                                         alt={`Amostra ${indice + 1}, temporária`}/>)}</div>
        <button className="primary wide" onClick={salvar}
                disabled={imagens.length !== 5 || !consentimento || processando}>{processando ? 'Salvando…' : 'Salvar referências criptografadas'}</button>
        {imagens.length > 0 && <button className="quiet" disabled={processando} onClick={() => {
          definirImagens([]);
          definirImagemCongelada(null);
          definirCaptura(null);
        }}>Descartar amostras e recomeçar</button>}
      </> : <>
        <h2>Recurso solicitado</h2>
        <p className="hint">O reconhecimento libera o cofre até o nível solicitado, respeitando as divisões do cadastro.</p>
        <label>Nível de acesso<select value={nivel} disabled={processando} onChange={evento => {
          definirNivel(Number(evento.target.value));
          definirDecisao(null);
        }}>
          <option value="1">1 — Acesso geral</option>
          <option value="2">2 — Divisão específica</option>
          <option value="3">3 — Exclusivo do ministro</option>
        </select></label>
        {nivel === 2 && <label>Divisão<input value={divisao} maxLength={60} onChange={evento => {
          definirDivisao(evento.target.value);
          definirDecisao(null);
        }} list="divisoes-cofre" placeholder="Ex.: florestas" disabled={processando}/></label>}
        <datalist id="divisoes-cofre">
          {['agua', 'solo', 'biodiversidade', 'florestas'].map(nome => <option key={nome} value={nome}/>)}
        </datalist>
        <div className={`decision ${decisao ? decisao.granted ? 'granted' : 'denied' : ''}`} aria-live="polite">
          <ScanFace size={28}/>
          <h3>{decisao ? decisao.granted ? 'Acesso autorizado' : 'Acesso negado' : 'Aguardando avaliação'}</h3>
          <p>{decisao ? traduzirMotivo(decisao.reason) : 'A identidade e as permissões serão verificadas a cada captura.'}</p>
          {decisao && <dl>
            <div>
              <dt>Identidade</dt>
              <dd>{decisao.subject_id ?? 'Não identificada'}</dd>
            </div>
            <div>
              <dt>Registro</dt>
              <dd>#{decisao.id} · persistido</dd>
            </div>
            <div>
              <dt>Tempo</dt>
              <dd>{decisao.elapsed_ms.toFixed(0)} ms</dd>
            </div>
          </dl>}
        </div>
      </>}
      {!pessoa && decisao?.granted && decisao.vault && <section className="vault" aria-label="Cofre ambiental">
        <div className="section-heading"><h2>Cofre ambiental</h2>
          <button className="quiet" onClick={() => definirDecisao(null)}>Fechar cofre</button>
        </div>
        <p className="vault-notice">{decisao.vault.notice}</p>
        <p className="hint">{decisao.vault.records.length} registros liberados. Retomar a câmera ou alterar o recurso exige nova captura.</p>
        {decisao.vault.records.map(registro => <article className="vault-record" key={registro.id}>
          <p className="muted">{registro.id} · Nível {registro.level} · {registro.division ?? (registro.level === 3 ? 'Exclusivo do ministro' : 'Acesso geral')}</p>
          <h3>{registro.title}</h3>
          <p className="vault-status">{registro.status} · {registro.location}</p>
          <p>{registro.summary}</p>
        </article>)}
      </section>}
      {erro && <p className="error" role="alert">{erro}</p>}
      {captura && <div className="processing"><h3>Processamento da captura</h3>
        <p>{traduzirMotivo(captura.status)}</p>
        <dl>
          <div>
            <dt>Rostos detectados</dt>
            <dd>{captura.faces.length}</dd>
          </div>
          <div>
            <dt>Iluminação média</dt>
            <dd>{captura.brightness?.toFixed(0) ?? '—'}</dd>
          </div>
          <div>
            <dt>Nitidez (Laplaciano)</dt>
            <dd>{captura.sharpness?.toFixed(0) ?? '—'}</dd>
          </div>
        </dl>
        {captura.aligned_image && <figure><img src={`data:image/jpeg;base64,${captura.aligned_image}`}
                                               alt="Região facial alinhada pelo SFace"/>
          <figcaption>Região alinhada<br/>112 × 112 px</figcaption>
        </figure>}
      </div>}
      <p className="privacy-note">Protótipo acadêmico. Sem detecção de vivacidade. Limiares de reconhecimento ainda em
        calibração.</p>
    </div>
  </section>;
}
