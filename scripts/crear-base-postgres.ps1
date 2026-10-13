# Crea la base de datos del aula virtual en PostgreSQL y escribe el archivo .env.
#
# Que hace:
#   1. Pide la clave del usuario "postgres" (se escribe aqui, no se guarda ni se muestra).
#   2. Crea el usuario "aula_app" (con clave al azar) y la base "aula_virtual_cetpro".
#   3. Escribe .env con la direccion de la base y una SECRET_KEY nueva.
#
# No toca ninguna otra base ni usuario de PostgreSQL. Si "aula_app" o la base ya existen, se detiene.
#
# Uso (desde la carpeta del proyecto):
#   powershell -ExecutionPolicy Bypass -File scripts\crear-base-postgres.ps1

param(
    [string]$Bin = "C:\Program Files\PostgreSQL\18\bin",
    [string]$Servidor = "localhost",
    [int]$Puerto = 5432,
    [string]$Base = "aula_virtual_cetpro",
    [string]$Rol = "aula_app"
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$psql = Join-Path $Bin "psql.exe"
$archivoEnv = Join-Path $raiz ".env"

if (-not (Test-Path $psql)) { throw "No encuentro psql.exe en $Bin. Usa -Bin con la carpeta bin de PostgreSQL." }
if (Test-Path $archivoEnv) { throw "Ya existe .env. Si quieres empezar de cero, renombralo o borralo y vuelve a correr este script." }

function Nueva-Clave([int]$largo, [string]$letras) {
    $bytes = New-Object byte[] $largo
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $salida = New-Object System.Text.StringBuilder
    foreach ($b in $bytes) { [void]$salida.Append($letras[$b % $letras.Length]) }
    return $salida.ToString()
}

function Consulta([string]$sql, [string]$bd = "postgres") {
    $r = & $psql -h $Servidor -p $Puerto -U postgres -d $bd -v ON_ERROR_STOP=1 -t -A -c $sql
    if ($LASTEXITCODE -ne 0) { throw "Fallo la consulta: $sql" }
    return ($r -join "").Trim()
}

$segura = Read-Host "Clave del usuario postgres" -AsSecureString
$env:PGPASSWORD = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura))

try {
    if ((Consulta "SELECT 1 FROM pg_roles WHERE rolname = '$Rol'") -eq "1") {
        throw "El usuario '$Rol' ya existe en PostgreSQL. No lo toco. Avisame para decidir que hacer."
    }
    if ((Consulta "SELECT 1 FROM pg_database WHERE datname = '$Base'") -eq "1") {
        throw "La base '$Base' ya existe en PostgreSQL. No la toco. Avisame para decidir que hacer."
    }

    $claveBase = Nueva-Clave 28 "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    $claveDjango = Nueva-Clave 60 "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"

    # CREATEDB: las pruebas automaticas crean y borran su propia base temporal (test_...).
    [void](Consulta "CREATE ROLE $Rol LOGIN CREATEDB PASSWORD '$claveBase'")
    [void](Consulta "CREATE DATABASE $Base OWNER $Rol ENCODING 'UTF8' TEMPLATE template0")
    Write-Host "Listo: usuario '$Rol' y base '$Base' creados."

    $ejemplo = Get-Content (Join-Path $raiz ".env.example") -Raw
    $env_ = $ejemplo -replace "(?m)^SECRET_KEY=.*$", "SECRET_KEY=$claveDjango"
    $env_ = $env_ -replace "(?m)^DATABASE_URL=.*$", "DATABASE_URL=postgres://${Rol}:${claveBase}@${Servidor}:${Puerto}/${Base}"
    [System.IO.File]::WriteAllText($archivoEnv, $env_, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Listo: archivo .env escrito (no se sube a Git)."
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
