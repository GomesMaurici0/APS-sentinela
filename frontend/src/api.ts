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

export class ApiError extends Error {
  constructor(public status: number, mensagem: string) { super(mensagem); }
}
export async function requisitarApi<T>(caminho: string, metodo = 'GET', corpo?: unknown): Promise<T> {
  const resposta = await fetch(`/api${caminho}`, {
    method: metodo, credentials: 'same-origin',
    headers: {
      ...(corpo !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (!resposta.ok) {
    const valor = await resposta.json().catch(() => ({ detail: 'Não foi possível concluir a operação.' }));
    throw new ApiError(resposta.status, typeof valor.detail === 'string' ? valor.detail : 'Dados inválidos.');
  }
  return resposta.status === 204 ? undefined as T : resposta.json();
}

export const rotulosMotivos: Record<string, string> = {
  acesso_autorizado: 'Permissão confirmada', nivel_insuficiente: 'Nível de permissão insuficiente',
  divisao_nao_autorizada: 'Divisão não autorizada', usuario_inativo: 'Usuário inativo',
  desconhecido: 'Rosto não reconhecido', ambiguo: 'Identidade ambígua', sem_referencias: 'Sem referências cadastradas',
  nenhum_rosto: 'Nenhum rosto detectado', multiplos_rostos: 'Mantenha apenas um rosto no quadro',
  rosto_pequeno: 'Aproxime-se da câmera', rosto_fora_do_quadro: 'Mantenha o rosto inteiro no quadro',
  iluminacao_baixa: 'Aumente a iluminação', iluminacao_alta: 'Reduza a iluminação direta',
  imagem_desfocada: 'Aguarde o foco da câmera', imagem_invalida: 'Imagem inválida',
  falha_biometrica: 'Falha no processamento biométrico', ok: 'Captura aprovada',
};
export function traduzirMotivo(motivo: string) { return rotulosMotivos[motivo] ?? motivo; }
export function formatarData(valor: string) { return new Date(valor).toLocaleString('pt-BR'); }
