export type Session = { username: string; csrf_token: string; expires_at: number };
export type Person = {
  subject_id: string; display_name: string; level: number; divisions: string[];
  active: boolean; sample_count: number; consent_at: string | null;
};
export type Capture = {
  status: string; brightness: number | null; sharpness: number | null; elapsed_ms: number;
  width: number | null; height: number | null; faces: number[][]; aligned_image: string | null;
};
export type Attempt = {
  id: number; occurred_at: string; subject_id: string | null; requested_level: number;
  division: string | null; granted: boolean; reason: string; similarity: number | null;
  elapsed_ms: number; capture?: Capture | null;
};
export type Stats = { users: number; enrolled: number; attempts: number; granted: number; denied: number };
export type Page<T> = { items: T[]; total: number; offset: number; limit: number };

let csrf = '';
export function setSession(value: Session | null) { csrf = value?.csrf_token ?? ''; }
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method, credentials: 'same-origin',
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(csrf && method !== 'GET' ? { 'X-CSRF-Token': csrf } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const value = await response.json().catch(() => ({ detail: 'Não foi possível concluir a operação.' }));
    if (response.status === 401 && path !== '/auth/login' && path !== '/auth/session') window.dispatchEvent(new Event('session-expired'));
    throw new ApiError(response.status, typeof value.detail === 'string' ? value.detail : 'Dados inválidos.');
  }
  return response.status === 204 ? undefined as T : response.json();
}

export const reasonLabel: Record<string, string> = {
  acesso_autorizado: 'Permissão confirmada', nivel_insuficiente: 'Nível de permissão insuficiente',
  divisao_nao_autorizada: 'Divisão não autorizada', usuario_inativo: 'Usuário inativo',
  desconhecido: 'Rosto não reconhecido', ambiguo: 'Identidade ambígua', sem_referencias: 'Sem referências cadastradas',
  nenhum_rosto: 'Nenhum rosto detectado', multiplos_rostos: 'Mantenha apenas um rosto no quadro',
  rosto_pequeno: 'Aproxime-se da câmera', rosto_fora_do_quadro: 'Mantenha o rosto inteiro no quadro',
  iluminacao_baixa: 'Aumente a iluminação', iluminacao_alta: 'Reduza a iluminação direta',
  imagem_desfocada: 'Aguarde o foco da câmera', imagem_invalida: 'Imagem inválida',
  falha_biometrica: 'Falha no processamento biométrico', ok: 'Captura aprovada',
};
export function label(reason: string) { return reasonLabel[reason] ?? reason; }
export function date(value: string) { return new Date(value).toLocaleString('pt-BR'); }
