import sqlite3

import numpy as np
import pytest
from cryptography.fernet import Fernet
from sentinela.autorizacao import UserPermission
from sentinela.galeria import Gallery


def samples():
    return [np.ones(128, np.float32)] * 5


def test_encrypted_roundtrip_and_delete(tmp_path):
    gallery = Gallery(tmp_path)
    gallery.enroll("voluntario_teste", UserPermission(1), samples(), consent=True)
    assert b"voluntario_teste" not in gallery.database.read_bytes()
    record = Gallery(tmp_path).read()["subjects"]["voluntario_teste"]
    assert len(record["samples"]) == 5
    assert record["consent_at"]
    gallery.delete("voluntario_teste")
    assert gallery.references() == {}


def test_consent_and_minimum_samples_required(tmp_path):
    gallery = Gallery(tmp_path)
    with pytest.raises(ValueError, match="Consentimento"):
        gallery.enroll("a", UserPermission(1), samples(), consent=False)
    with pytest.raises(ValueError, match="amostras"):
        gallery.enroll("a", UserPermission(1), samples()[:1], consent=True)
    assert not gallery.database.exists()


def test_duplicate_is_not_overwritten(tmp_path):
    gallery = Gallery(tmp_path)
    gallery.enroll("a", UserPermission(1), samples(), consent=True)
    with pytest.raises(ValueError, match="já cadastrado"):
        gallery.enroll("a", UserPermission(3), samples(), consent=True)
    assert gallery.read()["subjects"]["a"]["level"] == 1


def test_missing_key_never_regenerated(tmp_path):
    gallery = Gallery(tmp_path)
    gallery.enroll("a", UserPermission(1), samples(), consent=True)
    gallery.key_path.unlink()
    with pytest.raises(ValueError, match="Chave"):
        gallery.enroll("b", UserPermission(1), samples(), consent=True)
    assert not gallery.key_path.exists()


def test_wrong_key_and_modified_ciphertext_fail_closed(tmp_path):
    gallery = Gallery(tmp_path)
    gallery.enroll("a", UserPermission(1), samples(), consent=True)
    original_key = gallery.key_path.read_bytes()
    gallery.key_path.write_bytes(Fernet.generate_key())
    with pytest.raises(ValueError, match="chave incorreta"):
        gallery.read()
    gallery.key_path.write_bytes(original_key)
    with sqlite3.connect(gallery.database) as connection:
        connection.execute("UPDATE vault SET payload=?", (b"tampered",))
    with pytest.raises(ValueError, match="corrompida"):
        gallery.read()


def test_two_instances_preserve_other_subjects(tmp_path):
    first, second = Gallery(tmp_path), Gallery(tmp_path)
    first.enroll("a", UserPermission(1), samples(), consent=True)
    second.enroll("b", UserPermission(3), samples(), consent=True)
    assert set(first.read()["subjects"]) == {"a", "b"}
