# TLS certificate expiring or expired

alerts: TLSCertificateExpiry, ProbeSSLCertExpiringSoon
owner: Identity-Platform

## Symptoms
Clients fail with x509 errors. Blackbox exporter reports days to expiry below threshold.

## Likely causes
- cert-manager renewal failed (DNS-01 or HTTP-01 challenge failing)
- Certificate was issued manually and nobody owned renewal

## Diagnosis
- `kubectl get certificate -A` and `kubectl describe certificate <name>`
- `openssl s_client -connect host:443 -servername host | openssl x509 -noout -dates`

## Remediation
1. Check cert-manager Certificate and CertificateRequest status for the failing challenge
2. Fix the DNS or ingress issue blocking the ACME challenge and trigger renewal with cmctl renew
3. For manually issued certificates, request a new certificate and update the Kubernetes secret
4. Add the certificate to blackbox exporter monitoring with a 21 day warning threshold
