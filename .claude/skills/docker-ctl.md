---
name: docker-ctl
description: Inspect containers, logs, and images via docker/podman
user_invocable: true
---

# Docker / Podman Control

Inspect and manage containers. Works with both `docker` and `podman` runtimes.

## Commands

### List running containers
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}"
```

### View container logs
```bash
docker logs --tail 100 -f <container>
```

### List images
```bash
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

### Inspect container details
```bash
docker inspect <container> --format '{{json .State}}' | python -m json.tool
docker inspect <container> --format '{{json .NetworkSettings.Networks}}' | python -m json.tool
```

### Container resource usage
```bash
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

## Notes

- On Fedora/Bazzite systems, use `podman` instead of `docker`
- Always prefer `--format` for parseable output
- Use `--tail N` to limit log output
