import React from 'react';
import {render} from 'ink';
import {Command} from 'commander';
import {App} from './components/App.js';

const program = new Command();

program
  .name('tiaga-ink')
  .description('Tiaga terminal UI rewrite with React and Ink')
  .option('-s, --session <name>', 'open a specific session');

program.parse(process.argv);

const options = program.opts<{session?: string}>();

render(<App initialSession={options.session} />);
