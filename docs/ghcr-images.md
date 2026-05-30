# Building multi-architecture Docker images with GitHub Actions

This repository contains a GitHub Actions workflow at:

```text
.github/workflows/docker-images.yml
```

It builds and publishes two multi-platform images to GitHub Container Registry:

```text
ghcr.io/syschelle/bpstracker-backend:latest
ghcr.io/syschelle/bpstracker-frontend:latest
```

Supported platforms:

```text
linux/amd64
linux/arm64
```

## First build

Push the workflow to GitHub:

```bash
git add .github/workflows/docker-images.yml docker-compose.images.yml deploy-images.sh docs/ghcr-images.md
git commit -m "Add GHCR multi-arch Docker image builds"
git push
```

Then open GitHub:

```text
Repository -> Actions -> Build Docker images
```

You can run it manually with **Run workflow**, or it will run automatically on pushes to `main`.

## Make packages public

After the first successful build, open:

```text
Repository -> Packages
```

Open each package and make it public if this is a public project.

If packages stay private, the production server must log in to GHCR:

```bash
echo "<GITHUB_TOKEN>" | docker login ghcr.io -u syschelle --password-stdin
```

## Deploy using prebuilt images

On the production server:

```bash
cd /opt/bpstracker
git pull
bash ./deploy-images.sh
```

This pulls the matching image for the current architecture automatically.

## Raspberry Pi

For Raspberry Pi 3/4/5 or Pi Zero 2, use a 64-bit OS if possible:

```bash
uname -m
```

Recommended output:

```text
aarch64
```

Docker then pulls the `linux/arm64` image automatically.
