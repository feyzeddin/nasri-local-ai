# GitHub Setup

## 1) Repository Oluşturma

`project` dizinindeyken:

```bash
git init
git add .
git commit -m "chore: bootstrap nasri monorepo"
```

GitHub CLI ile:

```bash
gh repo create nasri --private --source . --remote origin --push
```

## 2) Branch Oluşturma

```bash
git checkout -b develop
git push -u origin develop
git checkout main
```

## 3) Branch Protection (GitHub UI)

`Settings > Branches > Add branch protection rule`

- Rule 1: `main`
  - Require a pull request before merging
  - Require approvals: 1
  - Require status checks to pass: `core-checks`
  - Do not allow bypassing
- Rule 2: `develop`
  - Require a pull request before merging
  - Require status checks to pass: `core-checks`

## 4) Önerilen Varsayılan Akış

- Yeni geliştirme: `feature/*` -> `develop`
- Yayın öncesi: `release/*` -> `main` (+ back-merge `develop`)
- Acil düzeltme: `hotfix/*` -> `main` (+ back-merge `develop`)
