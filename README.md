# GitHub Downloader

A tool for downloading repositories and files from GitHub.

## Features

- Download entire GitHub repositories as ZIP archives
- Clone repositories via Git
- Download individual files or directories
- Support for public and private repositories (with authentication)

## Installation

```bash
pip install github-downloader
```

## Usage

```bash
# Download a repository
github-downloader https://github.com/owner/repo

# Download a specific branch
github-downloader https://github.com/owner/repo --branch main

# Download a specific file
github-downloader https://github.com/owner/repo/blob/main/path/to/file
```

## Configuration

Set your GitHub personal access token to access private repositories:

```bash
export GITHUB_TOKEN=your_token_here
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](LICENSE)
