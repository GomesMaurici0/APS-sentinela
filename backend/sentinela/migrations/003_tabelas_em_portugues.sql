ALTER TABLE users RENAME TO usuarios;
ALTER TABLE user_divisions RENAME TO divisoes_usuarios;
ALTER TABLE biometric_references RENAME TO referencias_biometricas;
ALTER TABLE attempts RENAME TO tentativas_acesso;

DROP INDEX attempts_time;
CREATE INDEX indice_tentativas_acesso ON tentativas_acesso(id DESC);

PRAGMA user_version=3;
