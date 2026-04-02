import React, {useEffect, useState} from 'react';
import {Text} from 'ink';

const FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

export function Spinner() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex(current => (current + 1) % FRAMES.length);
    }, 80);

    return () => clearInterval(timer);
  }, []);

  return <Text color="green">{FRAMES[index]}</Text>;
}
