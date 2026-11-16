import {useEffect, useRef, useState} from 'react';
import {Camera as CameraIcon, CameraOff, ScanFace, X} from 'lucide-react';
import {api, Attempt, Capture, label, Person} from './api';

type Props = { person?: Person; onSaved?: () => void; onCancel?: () => void; onAttempt?: () => void };

export function Camera({person, onSaved, onCancel, onAttempt}: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const generation = useRef(0);
  const alive = useRef(true);
  const pending = useRef(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [images, setImages] = useState<string[]>([]);
  const [capture, setCapture] = useState<Capture | null>(null);
  const [frozen, setFrozen] = useState<string | null>(null);
  const [decision, setDecision] = useState<Attempt | null>(null);
  const [level, setLevel] = useState(1);
  const [division, setDivision] = useState('');
  const [consent, setConsent] = useState(false);

  function stop() {
    generation.current++;
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    setRunning(false);
    setFrozen(null);
    setImages([]);
    setCapture(null);
    setDecision(null);
  }

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      generation.current++;
      stream.current?.getTracks().forEach(track => track.stop());
    };
  }, []);

  async function start() {
    setError('');
    const id = ++generation.current;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Câmera indisponível. Abra pelo endereço local indicado.');
      const media = await navigator.mediaDevices.getUserMedia({video: {width: 640, height: 480}, audio: false});
      if (!alive.current || id !== generation.current) {
        media.getTracks().forEach(track => track.stop());
        return;
      }
      stream.current = media;
      if (video.current) {
        video.current.srcObject = media;
        await video.current.play();
      }
      media.getVideoTracks()[0].addEventListener('ended', () => {
        if (alive.current && generation.current === id) {
          stop();
          setError('A câmera foi desconectada. Inicie novamente.');
        }
      });
      setRunning(true);
    } catch (e) {
      stream.current?.getTracks().forEach(track => track.stop());
      stream.current = null;
      if (alive.current) setError(e instanceof DOMException ? 'Não foi possível abrir a câmera. Verifique a permissão e outros aplicativos.' : (e as Error).message);
    }
  }

  async function take() {
    if (pending.current || !video.current || !running) return;
    const source = video.current;
    if (!source.videoWidth) {
      setError('Aguarde a câmera iniciar.');
      return;
    }
    if (!person && level === 2 && !division.trim()) {
      setError('Informe a divisão solicitada.');
      return;
    }
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, 640 / Math.max(source.videoWidth, source.videoHeight));
    canvas.width = Math.round(source.videoWidth * scale);
    canvas.height = Math.round(source.videoHeight * scale);
    canvas.getContext('2d')!.drawImage(source, 0, 0, canvas.width, canvas.height);
    const image = canvas.toDataURL('image/jpeg', .85).split(',')[1];
    const id = generation.current;
    pending.current = true;
    setBusy(true);
    setError('');
    setDecision(null);
    setCapture(null);
    setFrozen(null);
    try {
      if (person) {
        const value = await api<Capture>('/biometrics/analyze', 'POST', {image});
        if (!alive.current || generation.current !== id) return;
        setCapture(value);
        setFrozen(image);
        if (value.status === 'ok') setImages(previous => [...previous, image]);
        else setError(label(value.status));
      } else {
        const value = await api<Attempt>('/attempts', 'POST', {
          image, requested_level: level, division: level === 2 ? division.trim() : null,
        });
        if (!alive.current || generation.current !== id) return;
        setDecision(value);
        setCapture(value.capture ?? null);
        setFrozen(image);
      }
    } catch (e) {
      if (alive.current && generation.current === id) setError((e as Error).message);
    } finally {
      pending.current = false;
      if (alive.current) {
        setBusy(false);
        if (!person) onAttempt?.();
      }
    }
  }

  async function save() {
    if (!person || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      await api(`/users/${person.subject_id}/biometrics`, 'POST', {images, consent});
      if (alive.current) {
        stop();
        onSaved?.();
      }
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      pending.current = false;
      if (alive.current) setBusy(false);
    }
  }

  return <section className="camera-workspace">
    <div className="camera-column">
      <div className="section-heading"><h2>{person ? `Referências de ${person.display_name}` : 'Captura facial'}</h2>
        {running && <button className="quiet" onClick={stop} disabled={busy}><CameraOff size={16}/> Desligar</button>}
      </div>
      <div className="viewfinder">
        <video ref={video} autoPlay muted playsInline className={running && !frozen ? '' : 'invisible'}/>
        {frozen && <img className="capture-image" src={`data:image/jpeg;base64,${frozen}`}
                        alt="Última captura, mantida somente em memória"/>}
        {frozen && capture?.width && capture.height &&
            <svg className="face-overlay" viewBox={`0 0 ${capture.width} ${capture.height}`}
                 aria-label="Localização facial">
              {capture.faces.map((face, i) => <g key={i}>
                <rect x={face[0]} y={face[1]} width={face[2]} height={face[3]}/>
                {[4, 6, 8, 10, 12].map(index => <circle key={index} cx={face[index]} cy={face[index + 1]} r="2"/>)}
              </g>)}
            </svg>}
        {!running &&
            <div className="camera-empty"><ScanFace size={56} strokeWidth={1}/><h3>Câmera desligada</h3><p>Ative para
              enquadrar um rosto.<br/>As imagens não serão gravadas.</p></div>}
        <span
            className="viewfinder-label">{running ? (frozen ? 'Última captura' : 'Prévia local') : 'Captura sob demanda'}</span>
      </div>
      <div className="camera-actions">
        {!running ?
            <button className="primary" onClick={start} disabled={!!person && !consent}><CameraIcon size={18}/> Ativar
              câmera</button>
            : frozen ? <button className="primary" onClick={() => {
                  setFrozen(null);
                  setCapture(null);
                  setError('');
                }} disabled={busy || (!!person && images.length >= 5)}>Retomar câmera</button>
                :
                <button className="primary" onClick={take} disabled={busy || (!!person && images.length >= 5)}><ScanFace
                    size={18}/>{busy ? 'Processando…' : person ? 'Coletar amostra' : 'Avaliar acesso'}</button>}
        {person && <button className="quiet" onClick={() => {
          stop();
          onCancel?.();
        }} disabled={busy}><X size={16}/> Cancelar cadastro</button>}
      </div>
      <p className="hint">Uma captura por ação. Mantenha o rosto inteiro, com boa iluminação.</p>
    </div>
    <div className="decision-column">
      {person ? <>
        <h2>Cadastro biométrico</h2><p className="muted">Colete cinco amostras com pequenas variações de pose. O
        cadastro só é salvo ao confirmar.</p>
        <label className="check"><input type="checkbox" checked={consent} disabled={running || busy}
                                        onChange={e => setConsent(e.target.checked)}/>
          O voluntário consentiu com o processamento facial local para a APS e foi informado sobre a exclusão e as
          limitações.</label>
        <div className="sample-progress"><strong>{images.length} <span>/ 5 amostras</span></strong>
          <progress max="5" value={images.length}/>
        </div>
        <div className="sample-strip">{images.map((image, index) => <img key={index}
                                                                         src={`data:image/jpeg;base64,${image}`}
                                                                         alt={`Amostra ${index + 1}, temporária`}/>)}</div>
        <button className="primary wide" onClick={save}
                disabled={images.length !== 5 || !consent || busy}>{busy ? 'Salvando…' : 'Salvar referências criptografadas'}</button>
        {images.length > 0 && <button className="quiet" disabled={busy} onClick={() => {
          setImages([]);
          setFrozen(null);
          setCapture(null);
        }}>Descartar amostras e recomeçar</button>}
      </> : <>
        <h2>Recurso solicitado</h2>
        <label>Nível de acesso<select value={level} disabled={busy} onChange={e => {
          setLevel(Number(e.target.value));
          setDecision(null);
        }}>
          <option value="1">1 — Acesso geral</option>
          <option value="2">2 — Divisão específica</option>
          <option value="3">3 — Exclusivo do ministro</option>
        </select></label>
        {level === 2 && <label>Divisão<input value={division} maxLength={60} onChange={e => {
          setDivision(e.target.value);
          setDecision(null);
        }} placeholder="Ex.: florestas" disabled={busy}/></label>}
        <div className={`decision ${decision ? decision.granted ? 'granted' : 'denied' : ''}`} aria-live="polite">
          <ScanFace size={28}/>
          <h3>{decision ? decision.granted ? 'Acesso autorizado' : 'Acesso negado' : 'Aguardando avaliação'}</h3>
          <p>{decision ? label(decision.reason) : 'A identidade e as permissões serão verificadas a cada captura.'}</p>
          {decision && <dl>
            <div>
              <dt>Identidade</dt>
              <dd>{decision.subject_id ?? 'Não identificada'}</dd>
            </div>
            <div>
              <dt>Registro</dt>
              <dd>#{decision.id} · persistido</dd>
            </div>
            <div>
              <dt>Tempo</dt>
              <dd>{decision.elapsed_ms.toFixed(0)} ms</dd>
            </div>
          </dl>}
        </div>
      </>}
      {error && <p className="error" role="alert">{error}</p>}
      {capture && <div className="processing"><h3>Processamento da captura</h3>
        <p>{label(capture.status)}</p>
        <dl>
          <div>
            <dt>Rostos detectados</dt>
            <dd>{capture.faces.length}</dd>
          </div>
          <div>
            <dt>Iluminação média</dt>
            <dd>{capture.brightness?.toFixed(0) ?? '—'}</dd>
          </div>
          <div>
            <dt>Nitidez (Laplaciano)</dt>
            <dd>{capture.sharpness?.toFixed(0) ?? '—'}</dd>
          </div>
        </dl>
        {capture.aligned_image && <figure><img src={`data:image/jpeg;base64,${capture.aligned_image}`}
                                               alt="Região facial alinhada pelo SFace"/>
          <figcaption>Região alinhada<br/>112 × 112 px</figcaption>
        </figure>}
      </div>}
      <p className="privacy-note">Protótipo acadêmico. Sem detecção de vivacidade. Limiares de reconhecimento ainda em
        calibração.</p>
    </div>
  </section>;
}
