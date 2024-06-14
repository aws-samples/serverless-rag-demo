// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { signIn, signUp } from './authService';
import Header from "@cloudscape-design/components/header";
import Container from "@cloudscape-design/components/container";

import Form from "@cloudscape-design/components/form";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Grid from "@cloudscape-design/components/grid";

const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const navigate = useNavigate();

  const handleSignIn = async (e: { preventDefault: () => void; }) => {
    e.preventDefault();
    try {
      const session = await signIn(email, password);
      console.log('Sign in successful', session);
      if (session && typeof session.AccessToken !== 'undefined') {
        sessionStorage.setItem('accessToken', session.AccessToken);
        if (sessionStorage.getItem('accessToken')) {
          window.location.href = '/chat';
        } else {
          console.error('Session token was not set properly.');
        }
      } else {
        console.error('SignIn session or AccessToken is undefined.');
      }
    } catch (error) {
      alert(`Sign in failed: ${error}`);
    }
  };

  const handleSignUp = async (e: { preventDefault: () => void; }) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      alert('Passwords do not match');
      return;
    }
    try {
      await signUp(email, password);
      navigate('/confirm', { state: { email } });
    } catch (error) {
      alert(`Sign up failed: ${error}`);
    }
  };

  return (

    <Grid
      gridDefinition={[{ colspan: 2 }, { colspan: 8 }, { colspan: 2 }]}
    >
      
      <div> </div>
      
      <div>
        <form onSubmit={isSignUp ? handleSignUp : handleSignIn}>

        <Form
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="primary">{isSignUp ? 'Sign Up' : 'Sign In'}</Button>
              <Button variant="link" onClick={() => setIsSignUp(!isSignUp)}>
                {isSignUp ? 'Already have an account? Sign In' : 'Need an account? Sign Up'}
              </Button>
             
            </SpaceBetween>
          }

        >
          <Container
            header={
              <Header variant='h1'> {isSignUp ? 'Sign up to create an account' : 'Sign in to your account'} </Header>

            }
          >
            <SpaceBetween direction="vertical" size="l">
              <FormField label="Email">
                <input className="inputText" id="email" type="email" value={email}
                  onChange={(e) => setEmail(e.target.value)} placeholder="Email" required />
              </FormField>
              <FormField label="Password">
                <input className="inputText" id="password" type="password" value={password}
                  onChange={(e) => setPassword(e.target.value)} placeholder="Password" required />
              </FormField>

              {isSignUp && (
                <FormField label="Confirm Password">
                  <input className="inputText" id="confirmPassword"
                    type="password" value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Confirm Password"
                    required
                  />
                </FormField>
              )}


            </SpaceBetween>
          </Container>
        </Form>
      </form>
      </div>
      <div></div>
    </Grid>



  );
};

export default LoginPage;
