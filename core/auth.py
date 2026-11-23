"""Usuarios y roles: consulta, funcionario, administrador.

Contraseñas con PBKDF2-SHA256 (biblioteca estándar), nunca en texto plano.
"""
import hashlib
import hmac
import secrets

from core import auditoria, db

ROLES = ("consulta", "funcionario", "administrador")
ITERACIONES = 240_000

# Qué puede hacer cada rol. Las páginas consultan esto antes de mostrar botones.
PERMISOS = {
    "consulta": {"ver_norma", "ver_parametros", "ver_cartografia"},
    "funcionario": {"ver_norma", "ver_parametros", "ver_cartografia",
                    "cargar_norma", "cargar_capa", "calcular", "expedientes",
                    "analizar_planos", "informes"},
    "administrador": {"*"},
}


def puede(rol: str, permiso: str) -> bool:
    p = PERMISOS.get(rol, set())
    return "*" in p or permiso in p


def _hash(clave: str, sal: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), ITERACIONES).hex()


def hay_usuarios() -> bool:
    return bool(db.consultar("SELECT 1 FROM usuarios LIMIT 1"))


def crear_usuario(usuario: str, nombre: str, rol: str, clave: str, creado_por: str) -> int:
    if rol not in ROLES:
        raise ValueError(f"Rol no válido: {rol}")
    if len(clave) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    sal = secrets.token_hex(16)
    uid = db.ejecutar(
        "INSERT INTO usuarios (usuario, nombre, rol, hash, sal) VALUES (?,?,?,?,?)",
        (usuario.strip().lower(), nombre.strip(), rol, _hash(clave, sal), sal),
    )
    auditoria.registrar(creado_por, "crear", "usuario", uid,
                        despues={"usuario": usuario, "nombre": nombre, "rol": rol})
    return uid


def verificar(usuario: str, clave: str) -> dict | None:
    filas = db.consultar("SELECT * FROM usuarios WHERE usuario = ? AND activo = 1",
                         (usuario.strip().lower(),))
    if not filas:
        return None
    u = filas[0]
    if hmac.compare_digest(u["hash"], _hash(clave, u["sal"])):
        auditoria.registrar(u["usuario"], "ingresar", "sesion")
        return {"id": u["id"], "usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"]}
    return None


def listar() -> list[dict]:
    return db.consultar("SELECT id, usuario, nombre, rol, activo, creado FROM usuarios ORDER BY usuario")


def cambiar_estado(uid: int, activo: bool, por: str) -> None:
    antes = db.consultar("SELECT usuario, activo FROM usuarios WHERE id=?", (uid,))
    db.ejecutar("UPDATE usuarios SET activo=? WHERE id=?", (1 if activo else 0, uid))
    auditoria.registrar(por, "editar", "usuario", uid, antes=antes[0] if antes else None,
                        despues={"activo": activo})


def cambiar_rol(uid: int, rol: str, por: str) -> None:
    if rol not in ROLES:
        raise ValueError(f"Rol no válido: {rol}")
    antes = db.consultar("SELECT usuario, rol FROM usuarios WHERE id=?", (uid,))
    db.ejecutar("UPDATE usuarios SET rol=? WHERE id=?", (rol, uid))
    auditoria.registrar(por, "editar", "usuario", uid, antes=antes[0] if antes else None,
                        despues={"rol": rol})
