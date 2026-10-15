"""Verifica os arquivos que poderiam ser enviados ao Git, sem imprimir valores."""
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = re.compile(r"(^|/)(?:\.env(?:\..*)?|private-config|\.idea)(?:/|$)|\.(?:pem|key|p8|p12|jks|keystore|dump|backup|sqlite3?)$|\.sql\.gz$")
DEPLOYMENT_HOST = re.compile(r"https?://[^\s\"'<>]*(?:" + "onrender" + r"\.com|up\." + "railway" + r"\.app)\b", re.I)
DB_SETTING = re.compile(r"^[ \t]*(?:POSTGRES_(?:DB|USER|PASSWORD)|FUT_MANAGER_DATABASE_(?:HOST|PORT|NAME|USER|PASSWORD|VOLUME))[ \t]*[:=][ \t]*(.+)$", re.M)
FIXED_PASSWORD = re.compile(r"\bpassword\s*=\s*['\"][^'\"]+['\"]")
DSN = re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s{}:'\"]+:[^\s{}@'\"]+@")


HTTP_URL = re.compile(r"https?://[a-zA-Z0-9.-]+(?::[0-9]+)?(?:/[^\s\"'`<>]*)?")
# Public documentation, standards and dependency registries are not deployment data.
PUBLIC_HOSTS = {
    'cryptography.io', 'cheatsheetseries.owasp.org',
    'docs.expo.dev', 'expo.dev', 'www.npmjs.com', 'registry.npmjs.org',
    'github.com', 'docs.github.com', 'chat.expo.dev', 'reactnative.dev',
    'www.w3.org', 'nativewind.dev', 'www.nativewind.dev', 'tamagui.dev',
    'reactnativeunistyles.vercel.app', 'railway.com', 'docs.railway.com', 'www.santosfc.com.br',
    'cdn.conmebol.com', 'www.cbf7.com.br', 'files.pythonhosted.org',
    'eslint.org', 'feross.org', 'opencollective.com', 'paypal.me',
    'tidelift.com', 'www.patreon.com',
}


def inspect_file(name, text):
    findings = []
    if name != '.env.example' and PRIVATE.search(name):
        findings.append((0, 'Arquivo privado incluído no Git'))
    for match in HTTP_URL.finditer(text):
        host = urlsplit(match.group(0)).hostname
        if host not in PUBLIC_HOSTS and not (name.startswith('tests/') and host == 'test'):
            findings.append((text.count('\n', 0, match.start()) + 1, 'URL absoluta fora das referências públicas permitidas'))
    for rule, message in [(DEPLOYMENT_HOST, 'Endereço de implantação fixado'), (DSN, 'Conexão com credenciais fixadas')]:
        for match in rule.finditer(text):
            findings.append((text.count('\n', 0, match.start()) + 1, message))
    if not name.startswith('tests/'):
        for match in FIXED_PASSWORD.finditer(text):
            findings.append((text.count('\n', 0, match.start()) + 1, 'Senha de execução fixada'))
    for match in DB_SETTING.finditer(text):
        value = match.group(1).strip().strip('"\'')
        if value and not value.startswith('${'):
            findings.append((text.count('\n', 0, match.start()) + 1, 'Valor de banco fixado na configuração'))
    if name == 'app.json' and re.search(r'"(?:projectId|package)"\s*:\s*"[^\"]+"', text):
        findings.append((0, 'Identidade de infraestrutura fixada no app.json'))
    return findings


def main():
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode().split('\0')
    findings = []
    for name in sorted(set(names)):
        if not name:
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            continue
        findings.extend((name, line, message) for line, message in inspect_file(name, text))
    for name, line, message in findings:
        print(f'{name}:{line}: {message} (valor omitido)')
    print(f'Revisão de configuração: {len(findings)} ocorrência(s).')
    return int(bool(findings))


if __name__ == '__main__':
    sys.exit(main())
