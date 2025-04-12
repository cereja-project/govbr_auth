from cryptography.fernet import Fernet


def generate_cript_verifier_secret():
    """
    Gera uma chave de criptografia Fernet válida de 32 bytes base64 (44 caracteres).
    A chave gerada pode ser usada para criptografar e descriptografar dados de forma segura.
    ex:
    >>> secret = generate_cript_verifier_secret()
    >>> len(secret)
    44
    :return: Uma string representando a chave de criptografia Fernet.
    """
    return Fernet.generate_key().decode('utf-8')